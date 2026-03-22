"use client";

interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface MiniCandleChartProps {
  candles: Candle[];
  entryPrice?: number | null;
  sl?: number | null;
  tp?: number | null;
  width?: number;
  height?: number;
  className?: string;
}

export default function MiniCandleChart({
  candles,
  entryPrice,
  sl,
  tp,
  height = 120,
  className = "",
}: MiniCandleChartProps) {
  if (!candles || candles.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-gray-600 text-xs ${className}`}
        style={{ height }}
      >
        No candle data
      </div>
    );
  }

  const padding = { top: 8, bottom: 8, left: 2, right: 2 };
  const chartHeight = height - padding.top - padding.bottom;

  // Collect all price values to determine range
  const allPrices: number[] = [];
  for (const c of candles) {
    allPrices.push(c.h, c.l);
  }
  if (entryPrice != null) allPrices.push(entryPrice);
  if (sl != null) allPrices.push(sl);
  if (tp != null) allPrices.push(tp);

  const minPrice = Math.min(...allPrices);
  const maxPrice = Math.max(...allPrices);
  const priceRange = maxPrice - minPrice || 1;

  // Map price to Y coordinate (inverted: higher price = lower Y)
  const priceToY = (price: number): number => {
    return padding.top + ((maxPrice - price) / priceRange) * chartHeight;
  };

  const candleCount = candles.length;

  // Grid lines (3 horizontal lines)
  const gridLines = [0.25, 0.5, 0.75].map((frac) => {
    const price = minPrice + priceRange * frac;
    return priceToY(price);
  });

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 100 ${height}`}
      preserveAspectRatio="none"
      className={className}
    >
      {/* Grid lines */}
      {gridLines.map((y, i) => (
        <line
          key={`grid-${i}`}
          x1={0}
          y1={y}
          x2={100}
          y2={y}
          stroke="#1e1e2e"
          strokeWidth={0.5}
        />
      ))}

      {/* Candlesticks */}
      {candles.map((candle, i) => {
        const candleWidth = (100 - padding.left - padding.right) / candleCount;
        const x = padding.left + i * candleWidth;
        const centerX = x + candleWidth / 2;
        const isUp = candle.c >= candle.o;
        const color = isUp ? "#00ff88" : "#ff4444";

        const wickTop = priceToY(candle.h);
        const wickBottom = priceToY(candle.l);
        const bodyTop = priceToY(Math.max(candle.o, candle.c));
        const bodyBottom = priceToY(Math.min(candle.o, candle.c));
        const bodyHeight = Math.max(bodyBottom - bodyTop, 0.5);
        const bodyWidth = Math.max(candleWidth * 0.6, 0.5);

        return (
          <g key={`candle-${i}`}>
            {/* Wick */}
            <line
              x1={centerX}
              y1={wickTop}
              x2={centerX}
              y2={wickBottom}
              stroke={color}
              strokeWidth={0.3}
            />
            {/* Body */}
            <rect
              x={centerX - bodyWidth / 2}
              y={bodyTop}
              width={bodyWidth}
              height={bodyHeight}
              fill={isUp ? color : color}
              opacity={isUp ? 0.9 : 0.9}
            />
          </g>
        );
      })}

      {/* Entry price line */}
      {entryPrice != null && (
        <line
          x1={0}
          y1={priceToY(entryPrice)}
          x2={100}
          y2={priceToY(entryPrice)}
          stroke="#00bfff"
          strokeWidth={0.5}
          strokeDasharray="2,1"
        />
      )}

      {/* Stop Loss line */}
      {sl != null && (
        <line
          x1={0}
          y1={priceToY(sl)}
          x2={100}
          y2={priceToY(sl)}
          stroke="#ff4444"
          strokeWidth={0.5}
          strokeDasharray="2,1"
        />
      )}

      {/* Take Profit line */}
      {tp != null && (
        <line
          x1={0}
          y1={priceToY(tp)}
          x2={100}
          y2={priceToY(tp)}
          stroke="#00ff88"
          strokeWidth={0.5}
          strokeDasharray="2,1"
        />
      )}
    </svg>
  );
}
