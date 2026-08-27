import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

function App() {
  const [dataset, setDataset] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [selectedQuery, setSelectedQuery] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [trace, setTrace] = useState(null);
  const [events, setEvents] = useState([]);
  const [version, setVersion] = useState("v1");
  const [diagnostics, setDiagnostics] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);

  const fetchOverallMetrics = async () => {
    try {
      const res = await fetch('/api/metrics/overall');
      const data = await res.json();
      setMetrics(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchDataset = async () => {
    try {
      const res = await fetch('/api/dataset');
      const data = await res.json();
      setDataset(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    const init = async () => {
      try {
        await fetch('/api/clear', { method: 'DELETE' });
        fetchDataset();
        fetchOverallMetrics();
      } catch (e) {
        console.error(e);
      }
    };
    init();
  }, []);

  const handleVersionChange = async (newVersion) => {
    setVersion(newVersion);
    setTrace(null);
    setEvents([]);
    await fetch('/api/clear', { method: 'DELETE' });
    fetchOverallMetrics();
  };

  const runDiagnostics = async () => {
    if (diagnosing) return;
    setDiagnosing(true);
    setDiagnostics(null);
    try {
      const res = await fetch(`/api/diagnose?version=${version}`);
      const data = await res.json();
      setDiagnostics(data.report);
    } catch (e) {
      console.error(e);
      setDiagnostics("Failed to fetch diagnostics.");
    }
    setDiagnosing(false);
  };

  const selectAndExecute = async (item) => {
    if (executing) return;
    setSelectedQuery(item);
    setExecuting(true);
    setTrace(null);
    setEvents([]);
    try {
      const res = await fetch('/api/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: item.query, expected_category: item.expected_category, version: version }),
      });
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line
        
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.type === 'done') { 
              setTrace(ev.trace); 
              fetchOverallMetrics();
              setExecuting(false);
              break; 
            }
            setEvents(prev => [...prev, ev]);
          } catch (e) { /* ignore */ }
        }
      }
    } catch (e) {
      console.error(e);
      setExecuting(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header__logo">
          <span className="header__logo-icon">🔍</span>
          <span className="header__logo-name">Agent<span>Observability</span></span>
          <span className="header__logo-tag">EVAL UI</span>
        </div>
        
        <div className="header__controls" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div className="version-toggle" style={{ display: 'flex', background: 'var(--bg-elevated)', borderRadius: '4px', overflow: 'hidden', border: '1px solid var(--border)' }}>
            <button 
              style={{ padding: '6px 12px', background: version === 'v1' ? 'var(--accent-a)' : 'transparent', color: version === 'v1' ? '#fff' : 'var(--text-secondary)', border: 'none', cursor: 'pointer', fontWeight: 600 }}
              onClick={() => handleVersionChange('v1')}
            >
              V1 (Baseline)
            </button>
            <button 
              style={{ padding: '6px 12px', background: version === 'v2' ? 'var(--success)' : 'transparent', color: version === 'v2' ? '#fff' : 'var(--text-secondary)', border: 'none', cursor: 'pointer', fontWeight: 600 }}
              onClick={() => handleVersionChange('v2')}
            >
              V2 (Optimized)
            </button>
          </div>
          <button 
            onClick={runDiagnostics}
            disabled={diagnosing}
            style={{ padding: '6px 16px', background: 'var(--accent-b)', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            {diagnosing ? 'Analyzing...' : 'Run Diagnostics'}
          </button>
        </div>
        <div className="header__status">
          <div style={{color: 'var(--text-muted)', fontSize: '12px', fontWeight: 'bold', marginRight: '8px', display: 'flex', alignItems: 'center'}}>
            SESSION AVERAGES:
          </div>
          <div className="metric-pill">
            <span>Router Accuracy:</span>
            <strong style={{ color: metrics.avg_router_accuracy <= 60 ? 'var(--error)' : 'inherit' }}>
              {metrics.avg_router_accuracy != null ? `${metrics.avg_router_accuracy.toFixed(1)}%` : '---'}
            </strong>
          </div>
          <div className="metric-pill">
            <span>Response Accuracy:</span>
            <strong style={{ color: metrics.avg_response_accuracy <= 3 ? 'var(--error)' : 'inherit' }}>
              {metrics.avg_response_accuracy != null ? `${metrics.avg_response_accuracy.toFixed(1)}/5` : '---'}
            </strong>
          </div>
          <div className="metric-pill">
            <span>Conciseness:</span>
            <strong style={{ color: metrics.avg_conciseness <= 3 ? 'var(--error)' : 'inherit' }}>
              {metrics.avg_conciseness != null ? `${metrics.avg_conciseness.toFixed(1)}/5` : '---'}
            </strong>
          </div>
        </div>
      </header>

      <main className="main">
        {/* Left Panel: Query List */}
        <div className="panel panel-left">
          <div className="panel-header">
            <span>Golden Dataset ({dataset.length})</span>
          </div>
          <div className="panel-content">
            {dataset.map((item, idx) => (
              <div 
                key={idx} 
                className={`query-item ${selectedQuery?.query === item.query ? 'active' : ''}`}
                onClick={() => selectAndExecute(item)}
              >
                <div className="query-text">{item.query}</div>
                <div className="query-meta">
                  <span className="tag tag-text">Expected: {item.expected_category}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel: Execution & Trace */}
        <div className="panel panel-main">
          <div className="panel-header">
            <span>Query Execution Trace (Current Query Scores)</span>
          </div>
          <div className="panel-content">
            {!selectedQuery ? (
              <div className="empty-state">Select a query from the left panel to execute.</div>
            ) : trace ? (
              <div className="trace-container">
                <div className="trace-metrics-banner">
                  <div className="metric-box">
                    <div className="metric-box-title">Router Accuracy</div>
                    <div className={`metric-box-val ${trace.router_accuracy_score === 100 ? 'val-good' : 'val-bad'}`}>
                      {trace.router_accuracy_score}%
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-box-title">RESPONSE ACCURACY</div>
                    <div className="metric-box-val" style={{ color: trace.response_accuracy_score <= 3 ? 'var(--error)' : 'var(--info)' }}>
                      {trace.response_accuracy_score != null ? `${trace.response_accuracy_score} / 5` : '-'}
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-box-title">CONCISENESS</div>
                    <div className="metric-box-val" style={{ color: trace.conciseness_score <= 3 ? 'var(--error)' : 'var(--accent-b)' }}>
                      {trace.conciseness_score != null ? `${trace.conciseness_score} / 5` : '-'}
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-box-title">Latency</div>
                    <div className="metric-box-val">{trace.total_latency?.toFixed(2)}s</div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-box-title">Total Tokens</div>
                    <div className="metric-box-val">{trace.spans?.reduce((sum, span) => sum + (span.total_tokens || 0), 0) || 0}</div>
                  </div>
                </div>

                <div className="trace-path">
                  <h3 style={{ marginBottom: '16px', color: 'var(--text-secondary)' }}>Execution Path</h3>
                  {trace.spans?.map((span, idx) => {
                     let out = {};
                     try {
                       const parsed = span.output_data ? JSON.parse(span.output_data) : null;
                       if (parsed) out = parsed;
                     } catch(e) {}
                     
                     return (
                      <div key={idx} className="trace-node">
                        <div className="trace-node-card">
                          <div className="trace-header">
                            <span className="trace-agent">{span.agent_name}</span>
                            <span className="trace-stats">{span.latency?.toFixed(2)}s | {span.total_tokens} tokens</span>
                          </div>
                          <div className="trace-output md-render">
                            {out.final_response && <ReactMarkdown>{out.final_response}</ReactMarkdown>}
                            {out.technical_response && <ReactMarkdown>{out.technical_response}</ReactMarkdown>}
                            {out.billing_response && <ReactMarkdown>{out.billing_response}</ReactMarkdown>}
                            {out.category && <span>Category: {out.category}</span>}
                          </div>
                        </div>
                      </div>
                     );
                  })}
                </div>
              </div>
            ) : executing ? (
               <div className="trace-container">
                  <div className="trace-path">
                  <h3 style={{ marginBottom: '16px', color: 'var(--text-secondary)' }}>Execution Path</h3>
                  {events.filter(e => e.type === 'node_complete').map((span, idx) => (
                    <div key={idx} className="trace-node">
                      <div className="trace-node-card">
                        <div className="trace-header">
                          <span className="trace-agent">{span.node}</span>
                          <span className="trace-stats">completed</span>
                        </div>
                        <div className="trace-output md-render">
                           {span.update?.final_response && <ReactMarkdown>{span.update.final_response}</ReactMarkdown>}
                           {span.update?.technical_response && <ReactMarkdown>{span.update.technical_response}</ReactMarkdown>}
                           {span.update?.billing_response && <ReactMarkdown>{span.update.billing_response}</ReactMarkdown>}
                           {span.update?.category && <span>Category: {span.update.category}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                  <div className="trace-node" style={{ padding: '24px 0 0 24px'}}>
                     <span className="spinner"></span>
                     <span style={{ marginLeft: '12px', color: 'var(--text-muted)'}}>Processing next agent / Judge LLM...</span>
                  </div>
                </div>
               </div>
            ) : (
              <div className="empty-state">
                <div style={{ marginBottom: '16px' }}>Ready to execute:</div>
                <div style={{ fontStyle: 'italic', color: 'var(--text-primary)' }}>"{selectedQuery.query}"</div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Diagnostics Modal */}
      {diagnostics && (
        <div className="modal-backdrop" onClick={() => setDiagnostics(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Diagnostics Report</h2>
              <button onClick={() => setDiagnostics(null)} className="close-btn">&times;</button>
            </div>
            <div className="modal-body md-render" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
              <ReactMarkdown>{diagnostics}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
