import Konva from "konva";
import { useEffect, useRef } from "react";
import { Layer, Rect, Stage, Text, Transformer } from "react-konva";
import { Link, useParams } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { useDocumentStatus, useEditSymbol, useSymbols } from "@/api/hooks";
import { useThemeColors } from "@/hooks/useThemeColors";
import { useCanvas } from "@/store/canvas";
import type { SymbolResponse } from "@/types/api";
import { PropertyEditor } from "./PropertyEditor";

function SymbolShape({
  symbol,
  selected,
  color,
  labelColor,
  onSelect,
  onChange,
}: {
  symbol: SymbolResponse;
  selected: boolean;
  color: string;
  labelColor: string;
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
        stroke={color}
        strokeWidth={selected ? 3 : 2}
        cornerRadius={3}
        fill={`${color}22`}
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
        y={symbol.bbox.y - 15}
        text={symbol.label ?? symbol.type}
        fontSize={12}
        fontStyle="bold"
        fill={labelColor}
      />
      {selected && (
        <Transformer ref={trRef} rotateEnabled keepRatio={false} anchorSize={8} borderStroke={color} />
      )}
    </>
  );
}

export function CanvasPage() {
  const { id = "" } = useParams();
  const { data: symbols } = useSymbols(id);
  const { data: status } = useDocumentStatus(id);
  const edit = useEditSymbol(id);
  const colors = useThemeColors();
  const { selectedIds, select, clearSelection, scale, setScale, position, setPosition } =
    useCanvas();

  const onWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    setScale(scale * (e.evt.deltaY > 0 ? 0.92 : 1.08));
  };

  const selectedSymbol = symbols?.find((s) => selectedIds.has(s.id)) ?? null;

  return (
    <div>
      <div className="page-title">
        <div className="row">
          <Link className="btn btn--ghost" to="/">← Documents</Link>
          <h2 style={{ margin: 0 }}>Symbol canvas</h2>
        </div>
        <div className="row">
          {status && <StatusBadge status={status.status} />}
          {status?.job && (
            <span className="hint">{status.job.stage} · {status.job.stage_status}</span>
          )}
          <Link className="btn btn--ghost" to={`/documents/${id}/graph`}>View graph →</Link>
        </div>
      </div>

      <div className="split">
        <div className="stack">
          <div className="canvas-frame">
            <Stage
              width={880}
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
              style={{ background: colors.bg }}
            >
              <Layer>
                {symbols?.map((s) => (
                  <SymbolShape
                    key={s.id}
                    symbol={s}
                    selected={selectedIds.has(s.id)}
                    color={colors.typeColor(s.type)}
                    labelColor={colors.label}
                    onSelect={(additive) => select(s.id, additive)}
                    onChange={(patch) => edit.mutate({ id: s.id, patch })}
                  />
                ))}
              </Layer>
            </Stage>
          </div>
          <p className="hint">
            Scroll to zoom · drag background to pan · shift-click to multi-select · drag / resize /
            rotate a symbol to edit (saved as a new version).
          </p>
        </div>
        <PropertyEditor symbol={selectedSymbol} typeColor={colors.typeColor} />
      </div>
    </div>
  );
}
