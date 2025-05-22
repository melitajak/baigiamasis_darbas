import React, { useEffect, useState, useCallback, useRef } from 'react';
import ReactFlow, {
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  MiniMap,
  Controls,
  Background,
} from 'reactflow';
import 'reactflow/dist/style.css';
import './App.css';
import FileNode from './FileNode';

const nodeTypes = { file: FileNode };

const FlowCanvas = () => {
  const reactFlowWrapper = useRef(null);
  const [tools, setTools] = useState({});
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [tempParams, setTempParams] = useState({});
  const [workflowName, setWorkflowName] = useState('');
  const [workflows, setWorkflows] = useState([]);
  const [executionLog, setExecutionLog] = useState([]);
  const [executionError, setExecutionError] = useState(null);
  const [originalWorkflowName, setOriginalWorkflowName] = useState(null);
  const [originalGraph, setOriginalGraph] = useState(null);  // new 
  const [toolSearch, setToolSearch] = useState('');


  const onConnect = useCallback((params) => {
    const newEdge = {
      ...params,
      id: `e-${params.source}-${params.target}-${+new Date()}`,
      data: {},
    };
    setEdges((eds) => addEdge(newEdge, eds));
  }, [setEdges]);

  const onNodeClick = (_event, node) => {
    setSelectedNode(node);
    setTempParams({ ...node.data.parameters });
  };

  const onDragStart = (event, toolName) => {
    event.dataTransfer.setData('application/reactflow', toolName);
    event.dataTransfer.effectAllowed = 'move';
  };

  const onDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  };

  const onDrop = (event) => {
    event.preventDefault();
    if (!reactFlowWrapper.current) return;

    const toolName = event.dataTransfer.getData('application/reactflow');
    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    const position = {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    };

    const newNode = {
      id: `${toolName}-${+new Date()}`,
      type: toolName === 'file' ? 'file' : 'default',
      position,
      data: {
        label: toolName,
        parameters: {},
        toolDef: tools[toolName] || {},
      },
      draggable: true,
    };
    setNodes((nds) => nds.concat(newNode));
  };

  const saveWorkflow = () => {
    if (!workflowName.trim()) {
      alert('Enter a workflow name.');
      return;
    }
  
    fetch('/tools/api/workflows/save/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: workflowName.trim(), graph: { nodes, edges } }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          alert('Workflow saved!');
          setWorkflowName('');
          setOriginalWorkflowName(null);
          loadWorkflowList();
        } else {
          alert(data.error || 'Error saving workflow.');
        }
      });
  };

  const loadWorkflowList = () => {
    fetch('/tools/api/workflows/')
      .then((res) => res.json())
      .then(setWorkflows);
  };

  const loadWorkflow = (wf) => {
    const updated = wf.graph.nodes.map((n) => ({
      ...n,
      draggable: true,
      data: {
        ...n.data,
        toolDef: tools[n.data.label] || {},
      },
    }));
    setNodes(updated);
    setEdges(wf.graph.edges);
    setWorkflowName(wf.name);
    setOriginalWorkflowName(wf.name);
    setOriginalGraph({ nodes: updated, edges: wf.graph.edges });
    setSelectedNode(null);
    setExecutionLog([]);
  };
  const validateMandatoryFields = () => {
  for (const node of nodes) {
    const toolDef = tools[node.data.label];
    if (!toolDef || !toolDef.options) continue;

    const parameters = node.data.parameters || {};
    const incoming = edges.filter(e => e.target === node.id);

    for (const opt of toolDef.options) {
      if (opt.mandatory) {
        const paramValue = parameters[opt.label];
        const edgeSupplied = incoming.some(e => e.data?.param === opt.label);

        if (
          (paramValue === undefined || paramValue === null || String(paramValue).trim() === '') &&
          !edgeSupplied
        ) {
          return {
            valid: false,
            message: `Missing mandatory input "${opt.label}" for tool "${node.data.label}"`,
          };
        }
      }
    }
  }

  return { valid: true };
};


  const runWorkflow = () => {
    setExecutionError(null); 
    setExecutionLog([]);     

    const check = validateMandatoryFields();
    if (!check.valid) {
      setExecutionError(check.message);
      return;
    }

    fetch('/tools/api/workflows/execute/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name: workflowName,
        nodes,
        edges,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          setExecutionError(null);
          setExecutionLog(data.log || []);
        } else {
          setExecutionError(data.error || "Workflow validation failed.");
          setExecutionLog([]);
        }
      })
      .catch((err) => {
        setExecutionError("Network error or server not reachable.");
        setExecutionLog([]);
      });
  };

  const deleteSelected = useCallback(() => {
    setNodes((nds) => nds.filter((n) => !n.selected));
    setEdges((eds) => eds.filter((e) => !e.selected));
    setSelectedNode(null);
  }, [setNodes, setEdges]);

  const commitTempParams = () => {
    if (!selectedNode) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, parameters: { ...tempParams } } }
          : n
      )
    );
    setSelectedNode(null);
  };

  const saveEditedWorkflow = () => {
    if (!originalWorkflowName) return;

    fetch('/tools/api/workflows/save/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: originalWorkflowName,
        graph: { nodes, edges }
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          alert('Workflow changes saved!');
          loadWorkflowList();
        } else {
          alert('Error saving changes.');
        }
      });
  };

  useEffect(() => {
    fetch('/tools/api/tools/')
      .then((res) => res.json())
      .then((data) => {
        const normalized = {};
        for (const [toolName, toolData] of Object.entries(data)) {
          const options = Array.isArray(toolData.options)
            ? toolData.options.map(opt => ({
                label: String(opt.label || ''),
                flag: opt.flag ?? null,
                type: opt.type || 'text'
              }))
            : [];

          normalized[toolName] = {
            description: toolData.description || '',
            command: toolData.command || '',
            options
          };
        }

        normalized['file'] = {
          description: 'File passthrough node',
          command: null,
          options: [{ label: 'filename', flag: null, type: 'text' }]
        };

        setTools(normalized);

        setNodes((prev) =>
          prev.map((n) => ({
            ...n,
            draggable: true,
            data: {
              ...n.data,
              toolDef: normalized[n.data.label] || {},
            },
          }))
        );
      });

    loadWorkflowList();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Delete') deleteSelected();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deleteSelected]);

  return (
    <>
      <div className="workflow-wrapper">
        <div className="tool-sidebar">
          <h6>🛠 Tools</h6>
          <input
            type="text"
            className="form-control form-control-sm mb-2"
            placeholder="Search tools..."
            value={toolSearch}
            onChange={(e) => setToolSearch(e.target.value)}
          />
          <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
            {Object.keys(tools)
              .filter(t => t !== 'file' && t.toLowerCase().includes(toolSearch.toLowerCase()))
              .map(tool => (
                <div
                  key={tool}
                  className="tool-draggable"
                  onDragStart={e => onDragStart(e, tool)}
                  draggable
                >
                  {tool}
                </div>
              ))}
          </div>

          <hr />
          <h6>📂 File Nodes</h6>
          <div className="tool-draggable file-node" onDragStart={(e) => onDragStart(e, 'file')} draggable>+ File</div>
          <hr />
          <h6>📁 Saved Workflows</h6>
          {workflows.map((wf) => (
          <div
            key={wf.id}
            className="workflow-item d-flex justify-content-between align-items-center mb-1 px-1"
            style={{ position: 'relative' }}
          >
            <button
              onClick={() => loadWorkflow(wf)}  
              className="btn btn-sm btn-outline-primary w-100 text-truncate pe-4"
              title={wf.name}
              style={{ position: 'relative' }}
            >
              {wf.name}
            </button>

            <span
              title="Duplicate"
              onClick={(e) => {
                e.stopPropagation();
                const newName = prompt(`Duplicate "${wf.name}" as:`);
                if (newName && newName.trim()) {
                  fetch('/tools/api/workflows/save/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName.trim(), graph: wf.graph }),
                  })
                    .then(res => res.json())
                    .then((data) => {
                      if (data.success) loadWorkflowList();
                      else alert(data.error || 'Error duplicating workflow.');
                    });
                }
              }}
              style={{
                position: 'absolute',
                right: 40,
                top: '53%',
                transform: 'translateY(-50%)',
                color: '#198754',
                zIndex: 10,
                cursor: 'pointer'
              }}
            >
              <i className="bi bi-files"></i>
            </span>

            <span
              className="workflow-delete"
              title="Delete"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`Delete workflow "${wf.name}"?`)) {
                  fetch('/tools/api/workflows/delete/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: wf.name }),
                  })
                    .then(res => res.json())
                    .then(() => loadWorkflowList());
                }
              }}
              style={{
                position: 'absolute',
                right: 15,
                top: '53%',
                transform: 'translateY(-50%)',
                color: '#507599',
                zIndex: 10,
              }}
            >
              <i className="bi bi-trash"></i>
            </span>
          </div>
        ))}
        </div>

        <div className="reactflow-container" ref={reactFlowWrapper} onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodeTypes={nodeTypes}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            fitView
            dragHandle=".drag-handle"
            panOnDrag
            panOnScroll
            zoomOnScroll
            zoomOnPinch
          >
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>

        {selectedNode && selectedNode.data.label !== 'file' && tools[selectedNode.data.label] && (
          <div className="config-panel right">
            <h5>{selectedNode.data.label} Options</h5>
            <table className="table table-sm table-borderless">
              <tbody>
                {tools[selectedNode.data.label].options.map((opt, i) => {
                  const incoming = edges.find(e => e.target === selectedNode.id && e.data?.param === opt.label);
                  const fileNode = incoming ? nodes.find(n => n.id === incoming.source) : null;
                  const isAuto = !!incoming;
                  const value = isAuto
                    ? fileNode?.data.parameters?.filename || ''
                    : tempParams[opt.label] || '';

                  return (
                    <tr key={i}>
                      <td>{opt.label}</td>
                      <td>
                        {opt.type === 'file' && !isAuto ? (
                          <input
                            type="file"
                            className="form-control form-control-sm"
                            onChange={(e) => {
                              const file = e.target.files[0];
                              if (file) {
                                setTempParams((prev) => ({
                                  ...prev,
                                  [opt.label]: file.name,
                                }));
                              }
                            }}
                          />
                        ) : (
                          <input
                            disabled={isAuto}
                            type={opt.type === 'number' ? 'number' : 'text'}
                            className="form-control form-control-sm"
                            value={value}
                            onChange={(e) =>
                              setTempParams((prev) => ({
                                ...prev,
                                [opt.label]: e.target.value,
                              }))
                            }
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <button className="btn btn-sm btn-primary me-2" onClick={commitTempParams}>Save</button>
            <button className="btn btn-sm btn-secondary" onClick={() => setSelectedNode(null)}>Cancel</button>
          </div>
        )}
      </div>

      {executionError && (
        <div className="alert alert-danger mx-3 mt-2" role="alert">
          <strong>Error:</strong> {executionError}
        </div>
      )}

      <div className="p-3">
        <input
          type="text"
          value={workflowName}
          onChange={(e) => setWorkflowName(e.target.value)}
          placeholder="Workflow name"
          className="form-control d-inline w-50 me-2"
        />

        {!originalWorkflowName && (
          <button onClick={saveWorkflow} className="btn btn-primary me-2">
            Save Workflow
          </button>
        )}

        {originalWorkflowName && (
          <button onClick={saveEditedWorkflow} className="btn btn-warning me-2">
            Save Changes
          </button>
        )}

        <button onClick={runWorkflow} className="btn btn-success me-2">
          Run Workflow
        </button>

        {originalWorkflowName && (
          <button
            onClick={() => {
              if (originalGraph) {
                setNodes(originalGraph.nodes);
                setEdges(originalGraph.edges);
                setSelectedNode(null);
                setExecutionLog([]);
              }
            }}
            className="btn btn-outline-secondary"
          >
            Revert Changes
          </button>
        )}
      </div>

      {executionLog.length > 0 && (
        <div className="mt-3 p-3">
          <h6>Execution Log:</h6>
          <pre style={{ background: '#f8f9fa', padding: '10px', maxHeight: '300px', overflowY: 'auto' }}>
            {executionLog.join('\n')}
          </pre>
        </div>
      )}
    </>
  );
};

const App = () => (
  <ReactFlowProvider>
    <FlowCanvas />
  </ReactFlowProvider>
);

export default App;