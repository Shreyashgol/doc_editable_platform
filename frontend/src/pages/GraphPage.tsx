import { Layer, Line, Stage, Text, Circle } from "react-konva";
import { useParams } from "react-router-dom";
import { useGraph } from "@/api/hooks";

// Simple radial layout: nodes on a circle, edges as connecting lines. A force layout could
// replace this without changing the data contract.
export function GraphPage() {
  const { id = "" } = useParams();
  const { data } = useGraph(id);
  if (!data) return <p>Loading graph…</p>;

  const cx = 450;
  const cy = 300;
  const radius = 220;
  const positions = new Map<string, { x: number; y: number }>();
  data.nodes.forEach((n, i) => {
    const angle = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
    positions.set(n.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
  });

  return (
    <div>
      <h2>Symbol graph</h2>
      <div style={{ border: "1px solid #ccc", width: 900 }}>
        <Stage width={900} height={600}>
          <Layer>
            {data.edges.map((e) => {
              const a = positions.get(e.source);
              const b = positions.get(e.target);
              if (!a || !b) return null;
              return (
                <Line key={e.id} points={[a.x, a.y, b.x, b.y]} stroke="#aaa" strokeWidth={1} />
              );
            })}
            {data.nodes.map((n) => {
              const p = positions.get(n.id)!;
              return (
                <>
                  <Circle key={n.id} x={p.x} y={p.y} radius={10} fill="#2980b9" />
                  <Text key={`${n.id}-t`} x={p.x + 12} y={p.y - 6} text={n.label ?? n.type} fontSize={11} />
                </>
              );
            })}
          </Layer>
        </Stage>
      </div>
      <p style={{ color: "#777", fontSize: 12 }}>
        {data.nodes.length} symbols · {data.edges.length} relationships
      </p>
    </div>
  );
}
