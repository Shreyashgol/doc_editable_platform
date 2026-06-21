import Konva from "konva";
import { useEffect, useRef } from "react";
import { Layer, Rect, Stage, Text, Transformer } from "react-konva";
import { useParams } from "react-router-dom";
import { useDocumentStatus, useEditSymbol, useSymbols } from "@/api/hooks";
import { useCanvas } from "@/store/canvas";
import type { SymbolResponse } from "@/types/api";
import { PropertyEditor } from "./PropertyEditor";

const TYPE_COLOR: Record<string, string> = {
  Valve: "#2980b9", Pump: "#27ae60", PressureVessel: "#8e44ad",
  HeatExchanger: "#d35400", PressureTransmitter: "#16a085", Controller: "#c0392b",
  Unknown: "#7f8c8d",
};

function SymbolShape({
  symbol,
  selected,
  onSelect,
  onChange,
}: {
  symbol: SymbolResponse;
  selected: boolean;
  onSelect: (additive: boolean) => void;
  onChange: (patch: Record<string, unknown>) => void;
}) {
  const ref = useRef<Konva.Rect>(null);
  const trRef = useRef<Konva.Transformer>(null);

  useEffect(() => {
    if (selected && ref.current && trRef.current) {
      trRef.current.nodes([ref.current]);
      trRef.current.getLayer()?.batchDraw();
    }
  }, [selected]);

  return (
    <>
      <Rect
        ref={ref}
        x={symbol.bbox.x}
        y={symbol.bbox.y}
        width={symbol.bbox.width}
        height={symbol.bbox.height}
        rotation={symbol.rotation}
        stroke={TYPE_COLOR[symbol.type] ?? "#333"}
        strokeWidth={2}
        fill={`${TYPE_COLOR[symbol.type] ?? "#333"}22`}
        draggable
        onClick={(e) => onSelect(e.evt.shiftKey)}
        onTap={() => onSelect(false)}
        onDragEnd={(e) => onChange({ bbox: { ...symbol.bbox, x: e.target.x(), y: e.target.y() } })}
        onTransformEnd={() => {
          const node = ref.current!;
          const scaleX = node.scaleX();
          const scaleY = node.scaleY();
          node.scaleX(1);
          node.scaleY(1);
          onChange({
            bbox: {
              x: node.x(),
              y: node.y(),
              width: Math.max(5, node.width() * scaleX),
              height: Math.max(5, node.height() * scaleY),
            },
            rotation: node.rotation(),
          });
        }}
      />
      <Text
        x={symbol.bbox.x}
        y={symbol.bbox.y - 14}
        text={symbol.label ?? symbol.type}
        fontSize={12}
        fill="#222"
      />
      {selected && <Transformer ref={trRef} rotateEnabled keepRatio={false} />}
    </>
  );
}

export function CanvasPage() {
  const { id = "" } = useParams();
  const { data: symbols } = useSymbols(id);
  const { data: status } = useDocumentStatus(id);
  const edit = useEditSymbol(id);
  const { selectedIds, select, clearSelection, scale, setScale, position, setPosition } =
    useCanvas();

  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const direction = e.evt.deltaY > 0 ? 0.92 : 1.08;
    setScale(scale * direction);
  };

  const selectedSymbol = symbols?.find((s) => selectedIds.has(s.id)) ?? null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 12 }}>
      <div>
        <p>
          Status: <strong>{status?.status ?? "…"}</strong>
          {status?.job && ` — ${status.job.stage} (${status.job.stage_status})`}
        </p>
        <div style={{ border: "1px solid #ccc" }}>
          <Stage
            width={900}
            height={620}
            scaleX={scale}
            scaleY={scale}
            x={position.x}
            y={position.y}
            draggable
            onWheel={onWheel}
            onDragEnd={(e) => setPosition({ x: e.target.x(), y: e.target.y() })}
            onMouseDown={(e) => {
              if (e.target === e.target.getStage()) clearSelection();
            }}
          >
            <Layer>
              {symbols?.map((s) => (
                <SymbolShape
                  key={s.id}
                  symbol={s}
                  selected={selectedIds.has(s.id)}
                  onSelect={(additive) => select(s.id, additive)}
                  onChange={(patch) => edit.mutate({ id: s.id, patch })}
                />
              ))}
            </Layer>
          </Stage>
        </div>
        <p style={{ color: "#777", fontSize: 12 }}>
          Scroll to zoom · drag background to pan · shift-click to multi-select · drag/resize/rotate a symbol to edit (saved as a new version).
        </p>
      </div>
      <PropertyEditor symbol={selectedSymbol} />
    </div>
  );
}
