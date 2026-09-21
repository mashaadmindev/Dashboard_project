const polarToCartesian = (cx, cy, r, angleDeg) => {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
};

const describeArc = (cx, cy, r, startAngle, endAngle) => {
  const start = polarToCartesian(cx, cy, r, startAngle);
  const end = polarToCartesian(cx, cy, r, endAngle);
  const largeArcFlag = Math.abs(startAngle - endAngle) > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
};

const DEFAULT_BANDS = [
  { limit: 70, color: "var(--teal)" },
  { limit: 90, color: "var(--amber)" },
  { limit: 100, color: "var(--danger)" },
];

// Semicircular speedometer-style gauge (0-100%), with colored risk bands and a needle.
export default function GaugeChart({ value = 0, sublabel = "", size = 220, bands = DEFAULT_BANDS }) {
  const clamped = Math.max(0, Math.min(100, value));
  const cx = size / 2;
  const cy = size / 2 + 6;
  const r = size / 2 - 24;
  const needleAngle = 180 - (clamped / 100) * 180;
  const needleTip = polarToCartesian(cx, cy, r - 14, needleAngle);

  let prevLimit = 0;
  const arcs = bands.map((band) => {
    const startAngle = 180 - (prevLimit / 100) * 180;
    const endAngle = 180 - (Math.min(band.limit, 100) / 100) * 180;
    prevLimit = band.limit;
    return { ...band, startAngle, endAngle };
  });

  const activeBand = bands.find((b) => value <= b.limit) || bands[bands.length - 1];

  return (
    <div className="gauge-chart" style={{ width: size }}>
      <svg viewBox={`0 0 ${size} ${cy + 22}`} width="100%" style={{ overflow: "visible" }}>
        {arcs.map((band, i) => (
          <path
            key={i}
            d={describeArc(cx, cy, r, band.startAngle, band.endAngle)}
            stroke={band.color}
            strokeWidth={14}
            fill="none"
          />
        ))}
        {[0, 25, 50, 75, 100].map((tick) => {
          const angle = 180 - (tick / 100) * 180;
          const pos = polarToCartesian(cx, cy, r + 18, angle);
          return (
            <text
              key={tick}
              x={pos.x}
              y={pos.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {tick}
            </text>
          );
        })}
        <line
          x1={cx}
          y1={cy}
          x2={needleTip.x}
          y2={needleTip.y}
          stroke="var(--ink)"
          strokeWidth={3}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={7} fill="var(--ink)" />
      </svg>
      <div className="gauge-chart-value" style={{ color: activeBand.color }}>
        {Math.round(value)}%
      </div>
      {sublabel && <div className="gauge-chart-sublabel">{sublabel}</div>}
    </div>
  );
}
