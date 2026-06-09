import { useCallback, useEffect, useRef, useState } from "react";
import "./Layout.css";

interface LayoutProps {
  left: React.ReactNode;
  right: React.ReactNode;
}

export function Layout({ left, right }: LayoutProps) {
  const [leftWidth, setLeftWidth] = useState(320);
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  // Window-level listeners so the drag survives the cursor leaving the
  // container (fast mouse moves, leaving the window and coming back).
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const next = Math.max(220, Math.min(e.clientX - rect.left, rect.width - 360));
      setLeftWidth(next);
    };
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [dragging]);

  return (
    <div className="layout" ref={containerRef}>
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
