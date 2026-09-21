import { useState, useRef, useEffect } from "react";
import { askFordAi } from "../api";

// Helper to format markdown (tables, bold, headers, lists, code) into clean React elements
function renderFormattedMarkdown(content) {
  if (!content) return null;
  const lines = content.split("\n");
  const elements = [];
  let inTable = false;
  let tableRows = [];
  let tableHeader = [];

  const flushTable = (key) => {
    if (tableRows.length > 0 || tableHeader.length > 0) {
      elements.push(
        <div className="ai-table-wrap" key={`table-${key}`}>
          <table className="ai-markdown-table">
            {tableHeader.length > 0 && (
              <thead>
                <tr>
                  {tableHeader.map((th, idx) => (
                    <th key={idx} dangerouslySetInnerHTML={{ __html: formatInline(th) }} />
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {tableRows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} dangerouslySetInnerHTML={{ __html: formatInline(cell) }} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      tableHeader = [];
      tableRows = [];
      inTable = false;
    }
  };

  const formatInline = (text) => {
    if (!text) return "";
    return text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    // Markdown Table handling
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      const cols = trimmed
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());

      // Separator row like | :--- | :---: |
      if (cols.every((c) => /^:?-+:?$/.test(c))) {
        return;
      }
      if (!inTable) {
        inTable = true;
        tableHeader = cols;
      } else {
        tableRows.push(cols);
      }
      return;
    } else if (inTable) {
      flushTable(index);
    }

    // Headings
    if (trimmed.startsWith("### ")) {
      elements.push(
        <h3 key={index} className="ai-heading-3">
          {trimmed.replace("### ", "")}
        </h3>
      );
    } else if (trimmed.startsWith("#### ")) {
      elements.push(
        <h4 key={index} className="ai-heading-4">
          {trimmed.replace("#### ", "")}
        </h4>
      );
    } else if (trimmed.startsWith("##### ")) {
      elements.push(
        <h5 key={index} className="ai-heading-5">
          {trimmed.replace("##### ", "")}
        </h5>
      );
    }
    // Bullet points
    else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      elements.push(
        <li
          key={index}
          className="ai-list-item"
          dangerouslySetInnerHTML={{ __html: formatInline(trimmed.substring(2)) }}
        />
      );
    }
    // Blank lines
    else if (!trimmed) {
      elements.push(<div key={index} style={{ height: "6px" }} />);
    }
    // Normal paragraphs
    else {
      elements.push(
        <p
          key={index}
          className="ai-paragraph"
          dangerouslySetInnerHTML={{ __html: formatInline(trimmed) }}
        />
      );
    }
  });

  if (inTable) {
    flushTable("final");
  }

  return elements;
}

export default function AskFordAiPage({ globalFilters }) {
  const [messages, setMessages] = useState([
    {
      id: "init",
      sender: "ai",
      text: "Hi. How can i assist you",
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    const queryText = input.trim();
    if (!queryText || loading) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: queryText,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

      const res = await askFordAi(queryText, historyPayload, globalFilters);
      const data = res.data;

      const aiMessage = {
        id: `ai-${Date.now()}`,
        sender: "ai",
        text: data.response || "No response received.",
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (err) {
      const errorMessage = {
        id: `err-${Date.now()}`,
        sender: "ai",
        text: `Error: ${err?.response?.data?.detail || err?.message || "Failed to reach AI service."}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: `init-${Date.now()}`,
        sender: "ai",
        text: "Hi. How can i assist you",
      },
    ]);
  };

  return (
    <div className="ai-page-container">
      {/* Simple Header */}
      <div className="ai-header-card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "20px" }}>🤖</span>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: "700", color: "var(--ink, #1e293b)" }}>
              Ask Ford data analysis AI
            </h2>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={clearChat}
            style={{ fontSize: "12px", padding: "4px 10px" }}
          >
            Clear
          </button>
        </div>
      </div>

      {/* Conversation Area */}
      <div className="ai-chat-messages-area">
        {messages.map((m) => (
          <div key={m.id} className={`ai-message-row ${m.sender === "user" ? "user-row" : "ai-row"}`}>
            {m.sender === "ai" && <div className="ai-chat-avatar">AI</div>}

            <div className={`ai-message-bubble ${m.sender === "user" ? "user-bubble" : "ai-bubble"}`}>
              <div className="ai-message-body">
                {m.sender === "user" ? <p style={{ margin: 0 }}>{m.text}</p> : renderFormattedMarkdown(m.text)}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="ai-message-row ai-row">
            <div className="ai-chat-avatar">AI</div>
            <div className="ai-message-bubble ai-bubble ai-loading-bubble">
              <div className="ai-typing-indicator">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="ai-input-wrapper">
        <form className="ai-input-form" onSubmit={handleSend}>
          <input
            type="text"
            className="ai-text-input"
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            autoFocus
          />
          <button type="submit" className="btn ai-send-btn" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
