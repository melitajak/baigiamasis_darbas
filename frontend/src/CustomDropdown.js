import React, { useState, useEffect, useRef } from 'react';
import './CustomDropdown.css';

const CustomDropdown = ({ value, options, onChange }) => {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  const toggle = (e) => {
    e.stopPropagation();
    setOpen(!open);
  };

  const handleSelect = (label) => {
    onChange(label);
    setOpen(false);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div
      className="custom-dropdown"
      ref={wrapperRef}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="dropdown-header" onClick={toggle}>
        <span>{value || 'Select input label'}</span>
        <span className="dropdown-arrow">▾</span>
    </div>
      {open && (
        <div className="dropdown-body">
          {options.length === 0 ? (
            <div className="dropdown-item disabled">No input labels</div>
          ) : (
            options.map((opt, idx) => (
              <div
                key={idx}
                className="dropdown-item"
                onClick={() => handleSelect(opt.label)}
              >
                {opt.label}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default CustomDropdown;