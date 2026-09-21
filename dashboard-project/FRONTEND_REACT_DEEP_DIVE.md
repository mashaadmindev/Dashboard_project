# Frontend Architecture & Technical Deep-Dive: Ford Fleet & KPI Dashboard

> **Target Audience**: Technical Leads, Senior React Architects, and Frontend Developers.  
> **Stack**: React 18.3.1 (Concurrent Root), Vite 5.4.6, Recharts 2.12.7, Axios 1.7.7, Vanilla CSS Design System.

---

## 1. High-Level Frontend Architecture

The frontend is a **Single Page Application (SPA)** built with **React 18** and bundled with **Vite**. It adopts a **Unidirectional Data Flow (Flux-style container pattern)** where top-level state is orchestrated in `App.jsx` and distributed down the component tree via explicit props.

```
                                    ┌──────────────────────┐
                                    │      main.jsx        │
                                    │ (React.StrictMode)   │
                                    └──────────┬───────────┘
                                               │
                                    ┌──────────▼───────────┐
                                    │       App.jsx        │
                                    │  (Root State Holder) │
                                    └────┬───┬───┬───┬───┬─┘
         ┌───────────────────────────────┘   │   │   │   └───────────────────────────────┐
         │                                   │   │   │                                   │
┌────────▼─────────────┐ ┌───────────────────▼──┐│┌──▼───────────────────┐ ┌─────────────▼────────────┐
│ UniversalFilterBar   │ │   Dashboard Page     │││  Team Wise Page      │ │   Glide Path Page          │
│ (Draft/Apply Pattern)│ │ ┌──────────────────┐ │││ ┌──────────────────┐ │ │ ┌────────────────────────┐ │
└──────────────────────┘ │ │ DashboardKpiRow  │ │││ │ TeamWiseByTeam   │ │ │ │ Dept Governance Card   │ │
                         │ ├──────────────────┤ │││ ├──────────────────┤ │ │ ├────────────────────────┤ │
                         │ │ AlertsPanel      │ │││ │ TeamWiseSection  │ │ │ │ Budget Strip (KPIs)    │ │
                         │ ├──────────────────┤ │││ │  - BarChart (Re) │ │ │ ├────────────────────────┤ │
                         │ │ DatasetSection   │ │││ │  - LineChart(Re) │ │ │ │ Trajectory Chart (Dual)│ │
                         │ │  - TeamPieChart  │ │││ └──────────────────┘ │ │ ├────────────────────────┤ │
                         │ │  - TrendChart    │ ││└──────────────────────┘ │ │ Excel Matrix (useMemo) │ │
                         │ │  - ChartBuilder  │ │                          │ └────────────────────────┘ │
                         │ └──────────────────┘ │                          └────────────────────────────┘
                         └──────────────────────┘
                                    │                                                    │
                         ┌──────────▼───────────┐                             ┌──────────▼───────────┐
                         │   FileUpload Page    │                             │   AskFordAiPage      │
                         │ (Drag & Drop + Ref)  │                             │ (useRef Chat + AI MD)│
                         └──────────────────────┘                             └──────────────────────┘
```

---

## 2. Core State Management & Data Flow Blueprint

### 2.1 Root State in `App.jsx`

`App.jsx` serves as the single source of truth for global session state:

| State Variable | Type | Purpose | How It Propagates |
| :--- | :--- | :--- | :--- |
| `page` | `string` | Active tab navigation (`"dashboard"`, `"teamwise"`, `"glidepath"`, `"upload"`, `"ai_analyst"`). | Dictates conditional rendering of main container. |
| `tables` | `Array<TableMeta>` | Metadata for all ingested Postgres tables (row counts, column types). | Passed to `DatasetSection`, `TeamWisePage` to detect table availability. |
| `globalFilters` | `Object` | `{ year: "", month: "", filters: { [column]: value } }` | Passed to every data-fetching component. |
| `refreshKey` | `number` | Monotonically increasing counter (`0, 1, 2...`). | Used as a cache-busting dependency in child `useEffect` hooks. |

```jsx
// App.jsx (State Definition & Cache Invalidation)
const [page, setPage] = useState("dashboard");
const [tables, setTables] = useState([]);
const [globalFilters, setGlobalFilters] = useState(EMPTY_GLOBAL_FILTERS);
const [refreshKey, setRefreshKey] = useState(0);

const handleUploaded = () => {
  loadTables();              // Refetch table schemas & row counts
  setRefreshKey((k) => k + 1); // Trigger refetch in all active visualizations
};
```

---

## 3. Detailed Component Breakdown & React Patterns

### 3.1 `UniversalFilterBar.jsx` — The Draft/Apply Pattern

#### The Problem It Solves:
In a dashboard with multiple filters (Year, Month, Team, Region, VCI), triggering a network request on every single dropdown change causes UI thrashing, race conditions, and heavy backend load.

#### Architectural Pattern: **Draft State vs. Committed State**
- `options`: Fetched once on mount via `Promise.all` across all available datasets, merged using Set unions.
- `draft`: Internal component state tracking uncommitted user selections.
- `value`: The committed global state passed down from `App.jsx`.
- `isDirty`: Computed as `JSON.stringify(draft) !== JSON.stringify(value)`. The "Apply" button is disabled until changes are made.

```jsx
// UniversalFilterBar.jsx
const isDirty = JSON.stringify(draft) !== JSON.stringify(value);
const apply = () => onChange(draft);
const reset = () => {
  setDraft(EMPTY_GLOBAL_FILTERS);
  onChange(EMPTY_GLOBAL_FILTERS);
};
```

---

### 3.2 `GlidePathPage.jsx` — Real-Time Simulation with `useMemo`

#### The Problem It Solves:
Department leads need to model vehicle additions (Build + Production) and disposals over 12 months to see if they meet year-end fleet reduction targets (e.g. -5% by December). When editing numbers, the UI must calculate running balances instantly without server roundtrips.

#### Key React Mechanics:
1. **In-Memory Running Balance Calculation (`useMemo`)**:
   - Starting Count = Prior Year Actual.
   - For each month: `Running = Running + (Build + Production) - Disposal`.
   - Wrapping this in `useMemo` ensures O(12) recalculation runs synchronously on keystrokes without unnecessary DOM thrashing.

```jsx
// GlidePathPage.jsx
const liveCalculatedMonthly = useMemo(() => {
  if (!data) return [];
  const actualStarting = isEditing
    ? (Number(editBudget.actual_amount) || 0)
    : (data.budget?.actual_amount ?? 0);
  let running = actualStarting;

  const sourceMonths = isEditing ? editMonths : (data.monthly || []);

  return sourceMonths.map((m) => {
    const b = Number(m.build_count) || 0;
    const p = Number(m.production_count) || 0;
    const d = Number(m.disposal_count) || 0;
    const adds = b + p;
    running = running + adds - d;

    return {
      ...m,
      build_count: b,
      production_count: p,
      total_adds: adds,
      disposal_count: d,
      total_monthly_count: running,
    };
  });
}, [data, isEditing, editMonths, editBudget.actual_amount]);
```

2. **Dual-Axis Recharts Visualization (`ComposedChart`)**:
   - `yAxisId="count"`: Left axis for line chart (`total_monthly_count`).
   - `yAxisId="bars"`: Right axis for additions & disposals bar clusters.
   - `ReferenceLine`: Dashed line marking the mandated December budget target.

---

### 3.3 `FileUpload.jsx` — Imperative DOM Access with `useRef`

#### Key React Mechanics:
- **Hidden Input Access**: Uses `const inputRef = useRef(null)` to trigger the hidden `<input type="file" />` programmatically from custom styled buttons (`inputRef.current.click()`).
- **Drag & Drop**: Native HTML5 Drag and Drop event listeners (`onDragOver`, `onDragLeave`, `onDrop`) with `e.preventDefault()` to prevent browser file opening.
- **Multipart Form Upload**: Serializes files into `FormData` and sends them via Axios with target destination table override options (`"auto"` or specific table).

---

### 3.4 `AskFordAiPage.jsx` — Auto-Scroll & Custom Markdown Parser

#### Key React Mechanics:
1. **Auto-Scroll with `useRef` & `scrollIntoView`**:
   ```jsx
   const messagesEndRef = useRef(null);
   useEffect(() => {
     messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
   }, [messages, loading]);
   ```
2. **Deterministic Markdown Parsing (`renderFormattedMarkdown`)**:
   - Parses streaming/received LLM text into native React JSX elements (`<table>`, `<h3>`, `<li>`, `<p>`).
   - Handles markdown tables (`| header | header |`) by tracking `inTable` state and flushing buffered rows.
   - Uses `dangerouslySetInnerHTML` only for inline formatting (`**bold**`, `*italic*`, `` `code` ``).

---

### 3.5 `colors.js` — Deterministic Color Mapping

#### The Problem It Solves:
In multi-chart dashboards, if "Team Powertrain" is Blue on one chart and Orange on another, it creates cognitive overload for users.

#### Solution:
- `METRIC_COLORS`: Static map for business entities (`arrival`, `disposal`, `budget`, etc.).
- `colorForTeam(team, teamOrder)`: Finds index of `team` in the canonically sorted `teamOrder` list and mods it against `TEAM_ACCENT_COLORS`. Ensures 100% visual consistency across tables, bar charts, and alerts.

---

## 4. Network & API Architecture (`api.js` + `vite.config.js`)

### 4.1 Axios Client Abstraction
All API interactions are centralized in `src/api.js`.
- Base URL is configured as `/api`.
- `buildParams()` serializes `{ year, month, filters }` into query params. Complex filter objects are passed as JSON strings: `params.filters = JSON.stringify(filters)`.

### 4.2 Dev Server Reverse Proxy
In `vite.config.js`, Vite runs a local reverse proxy to forward `/api` requests to FastAPI on `http://127.0.0.1:8000`.
- **Benefit**: Eliminates CORS (Cross-Origin Resource Sharing) issues during local development.

```js
// vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
```

---

## 5. Senior Lead Interview & Code Review Q&A

Here are the exact technical questions your React lead is likely to ask, along with the precise senior-level answers:

---

### Q1: *"Why did you lift state to `App.jsx` instead of using Redux, Zustand, or the Context API?"*
> **Senior Answer**:  
> *"For this application's current scope, the global state footprint is minimal: `page` (routing), `tables` (metadata), `globalFilters` (filter state), and `refreshKey` (invalidation token).  
> Lifting state to `App.jsx` adheres to the **YAGNI (You Aren't Gonna Need It)** principle and avoids unnecessary boilerplate. State is only 1-2 levels deep, so prop drilling is negligible.  
> If the application grows to include user auth tokens, theme preferences, and multi-step complex workflows, migrating `globalFilters` to a `FilterContext` or Zustand store would be the next logical refactor."*

---

### Q2: *"Why are you using `refreshKey` in `useEffect` dependency arrays instead of React Query / SWR?"*
> **Senior Answer**:  
> *"We implemented `refreshKey` as a lightweight dependency trigger. When a user uploads a new Excel file, child components (which are already mounted and listening to `globalFilters`) wouldn't otherwise know that the database contents changed. Incrementing `refreshKey` forces those `useEffect` hooks to re-fetch fresh data.  
> However, in a production evolution, replacing this pattern with **TanStack Query (React Query)** would give us automatic cache invalidation (`queryClient.invalidateQueries()`), request deduplication, background re-fetching, and built-in loading/error states."*

---

### Q3: *"How does `useMemo` in `GlidePathPage.jsx` optimize performance?"*
> **Senior Answer**:  
> *"In `GlidePathPage.jsx`, the user can edit monthly build, production, and disposal counts in real time. The running fleet count is a cumulative formula (`running = running + adds - disposal`).  
> By using `useMemo([data, isEditing, editMonths, editBudget.actual_amount])`, the calculation runs synchronously during render only when input values change. This allows the matrix table and the Recharts trajectory graph to update at 60fps as the user types, without dispatching redundant state setters or API calls."*

---

### Q4: *"Why did you use `Promise.all` in `UniversalFilterBar.jsx`?"*
> **Senior Answer**:  
> *"The dashboard supports multiple datasets (`arrival`, `disposal`, `niv_sheet_arrival`, etc.), each having different columns. We execute `Promise.all` on mount to fetch filter schemas concurrently rather than sequentially.  
> We also attach `.catch(() => null)` to each promise so that if one table hasn't been uploaded yet, the other requests still resolve successfully. The `mergeFilterOptions()` helper then aggregates distinct years, months, and categorical dimensions into unified dropdowns."*

---

### Q5: *"In `AskFordAiPage.jsx`, why did you write a custom markdown parser instead of importing `react-markdown`?"*
> **Senior Answer**:  
> *"A custom parser (`renderFormattedMarkdown`) was implemented to keep the client bundle lightweight and zero-dependency, specifically parsing standard markdown tables, lists, and headers directly into styled React components.  
> For production enterprise usage with arbitrary LLM output, swapping this with `react-markdown` + `remark-gfm` combined with `DOMPurify` would be preferable to guarantee protection against XSS attack vectors."*

---

### Q6: *"How do you handle chart responsiveness with Recharts?"*
> **Senior Answer**:  
> *"All charts (`BarChart`, `LineChart`, `PieChart`, `ComposedChart`) are wrapped inside Recharts' `<ResponsiveContainer width="100%" height={...}>`. This attaches a ResizeObserver to the parent DOM container, ensuring the SVG dynamically resizes when the browser window changes or when the sidebar collapses."*

---

### Q7: *"What happens during a re-render in `DatasetSection.jsx`?"*
> **Senior Answer**:  
> *"`DatasetSection` depends on `[table, globalFilters, refreshKey]`. When `globalFilters` changes, `useEffect` sets `kpis` to `null` and triggers `fetchKpis`. Meanwhile, its child components (`TeamPieChart`, `TrendChart`, `ChartBuilder`) receive the updated `globalFilters` as props and trigger their own targeted chart queries independently. React 18 batches these state updates to prevent layout thrashing."*

---

## 6. Recommended Next Steps for Enterprise Scaling

If asked *"What would you improve or refactor next?"*, mention these 4 senior architectural improvements:

1. **State & Caching Layer**: Adopt **TanStack Query (React Query)** to replace manual `useEffect` data fetching and eliminate `refreshKey`.
2. **Type Safety**: Migrate `.jsx` files to **TypeScript (`.tsx`)** with strict interfaces for API responses (e.g., `GlidepathPayload`, `FilterState`, `TableMeta`).
3. **Client-Side Routing**: Replace `page` string state with **React Router (`v6`)** or TanStack Router for bookmarkable URLs and browser history support (`/dashboard`, `/glidepath`, `/ai-analyst`).
4. **Component Modularization**: Extract atomic UI primitives (`Button`, `Card`, `Select`, `Badge`, `Modal`) into a dedicated `components/ui/` design system folder.
