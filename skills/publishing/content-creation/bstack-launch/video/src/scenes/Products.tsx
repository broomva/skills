import {
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { products, BRAND } from "../data/stack";

export const ProductsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({ frame, fps, config: { damping: 200 } });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: BRAND.bgDark,
        padding: 60,
      }}
    >
      <div
        style={{
          opacity: titleSpring,
          transform: `translateY(${interpolate(titleSpring, [0, 1], [30, 0])}px)`,
          fontSize: 20,
          fontWeight: 600,
          color: BRAND.aiBlue,
          textTransform: "uppercase",
          letterSpacing: 4,
          marginBottom: 40,
        }}
      >
        Built on the Stack
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 20,
          width: "100%",
          maxWidth: 800,
        }}
      >
        {products.map((product, i) => {
          const cardSpring = spring({
            frame: frame - 10 - i * 8,
            fps,
            config: { damping: 200 },
          });
          return (
            <div
              key={product.name}
              style={{
                opacity: cardSpring,
                transform: `translateX(${interpolate(cardSpring, [0, 1], [-40, 0])}px)`,
                background: BRAND.bgCard,
                border: `1px solid ${BRAND.glassBorder}`,
                borderRadius: 16,
                padding: "20px 28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: 26,
                    fontWeight: 700,
                    color: BRAND.textPrimary,
                  }}
                >
                  {product.name}
                </div>
                <div
                  style={{
                    fontSize: 16,
                    color: BRAND.textSecondary,
                    marginTop: 4,
                  }}
                >
                  {product.desc}
                </div>
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: BRAND.aiBlue,
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                }}
              >
                {product.tech}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
