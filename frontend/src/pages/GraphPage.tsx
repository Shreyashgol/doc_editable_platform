import { Circle, Layer, Line, Stage, Text } from "react-konva";
import { Link, useParams } from "react-router-dom";
import { useGraph } from "@/api/hooks";
import { useThemeColors } from "@/hooks/useThemeColors";

// Radial layout: nodes on a circle, edges as connecting lines. A force layout could replace
// this without changing the data contract.
export function GraphPage() {
  const { id = "" } = useParams();
  const { data } = useGraph(id);
  const colors = useThemeColors();

  return (
    <div>
      <div className="page-title">
        <div className="row">
          <Link className="btn btn--ghost" to={`/documents/${id}/canvas`}>← Canvas</Link>
          <h2 style={{ margin: 0 }}>Symbol graph</h2>
        </div>
        {data && (
          <span className="hint">{data.nodes.length} symbols · {data.edges.length} relationships</span>
        )}
      </div>

      {!data ? (
        <p className="muted">Loading graph…</p>
      ) : (
        <div className="canvas-frame">
          <Stage width={880} height={600} style={{ background: colors.bg }}>
            <Layer>
              {(() => {
                const cx = 440, cy = 300, radius = 220;
                const pos = new Map<string, { x: number; y: number }>();
                data.nodes.forEach((n, i) => {
                  const a = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
                  pos.set(n.id, { x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) });
                });
                return (
                  <>
                    {data.edges.map((e) => {
                      const a = pos.get(e.source), b = pos.get(e.target);
                      if (!a || !b) return null;
                      return <Line key={e.id} points={[a.x, a.y, b.x, b.y]} stroke={colors.grid} strokeWidth={1.5} />;
                    })}
                    {data.nodes.map((n) => {
                      const p = pos.get(n.id)!;
                      return (
                        <Circle key={n.id} x={p.x} y={p.y} radius={11} fill={colors.typeColor(n.type)} />
                      );
                    })}
                    {data.nodes.map((n) => {
                      const p = pos.get(n.id)!;
                      return (
                        <Text key={`${n.id}-t`} x={p.x + 14} y={p.y - 6}
                          text={n.label ?? n.type} fontSize={11} fill={colors.label} />
                      );
                    })}
                  </>
                );
              })()}
            </Layer>
          </Stage>
        </div>
      )}
      {data && data.edges.length === 0 && (
        <p className="hint">
          No relationships yet — these are inferred from classified symbols (enable OCR so symbols
          get labelled &amp; classified), or add edges via the API.
        </p>
      )}
    </div>
  );
}
