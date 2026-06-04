import { useCallback, useRef, useState } from "react";
import "./Layout.css";

interface LayoutProps {
  left: React.ReactNode;
  right: React.ReactNode;
}

export function Layout({ left, right }: LayoutProps) {
  const [leftWidth, setLeftWidth] = useState(320);
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const onDividerMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setDragging(true);
    },
    [],
  );

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const next = Math.max(200, Math.min(e.clientX - rect.left, rect.width - 300));
      setLeftWidth(next);
    },
    [dragging],
  );

  const stopDrag = useCallback(() => setDragging(false), []);

  return (
    <div
      className="layout"
      ref={containerRef}
      onMouseMove={onMouseMove}
      onMouseUp={stopDrag}
      onMouseLeave={stopDrag}
      style={{ cursor: dragging ? "col-resize" : undefined }}
    >
      <div className="layout-left" style={{ width: leftWidth }}>
        {left}
      </div>
      <div
        className={`layout-divider${dragging ? " dragging" : ""}`}
        onMouseDown={onDividerMouseDown}
      />
      <div className="layout-right">{right}</div>
    </div>
  );
}
