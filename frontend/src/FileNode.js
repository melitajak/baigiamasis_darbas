import React from 'react';
import { Handle, Position, useReactFlow } from 'reactflow';
import CustomDropdown from './CustomDropdown';
import './CustomDropdown.css';

const FileNode = ({ id, data }) => {
  const { getEdges, setEdges, getNodes } = useReactFlow();

  const connectedEdge = getEdges().find((e) => e.source === id);
  const connectedTool = connectedEdge
    ? getNodes().find((n) => n.id === connectedEdge.target)
    : null;

  const fileOptions = connectedTool?.data?.toolDef?.options?.filter(
    (opt) => opt.type === 'file'
  ) || [];

  const handleFileNameChange = (e) => {
    data.parameters.filename = e.target.value;
  };

  const handleLabelChange = (newLabel) => {
    setEdges((eds) =>
      eds.map((e) =>
        e.source === id ? { ...e, data: { ...e.data, param: newLabel } } : e
      )
    );
  };

  const selectedLabel =
    connectedEdge?.data?.param && fileOptions.some(opt => opt.label === connectedEdge.data.param)
      ? connectedEdge.data.param
      : '';

  return (
    <div
      style={{
        padding: '16px 10px',  
        border: '2px solid #4c8df6',
        borderRadius: '40px',
        background: '#eef3ff',
        textAlign: 'center',
        width: 180,
        fontSize: 12,
        position: 'relative',
        boxShadow: '0 0 0 2px #b6ceff',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        alignItems: 'center',
        minHeight: 130  
      }}
    >
      <Handle type="target" position={Position.Top} />

      <div
        className="drag-handle"
        style={{
          fontWeight: 'bold',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          cursor: 'grab',
          width: '100%',
          justifyContent: 'center',
          borderBottom: '1px solid #ccc',
          paddingBottom: 4
        }}
      >
        <span role="img" aria-label="file">📄</span> File
      </div>

      <div style={{ width: '100%' }}>
        <input
          type="text"
          defaultValue={data.parameters?.filename}
          onChange={handleFileNameChange}
          placeholder="filename"
          className="form-control form-control-sm"
          style={{ fontSize: '12px' }}
        />
      </div>

      <div style={{ width: '100%' }}>
        <CustomDropdown
          value={selectedLabel}
          options={fileOptions}
          onChange={handleLabelChange}
        />
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default FileNode;