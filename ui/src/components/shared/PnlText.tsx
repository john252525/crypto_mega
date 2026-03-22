"use client";

interface PnlTextProps {
  value: number;
  suffix?: "%" | "$" | "";
  className?: string;
}

export default function PnlText({
  value,
  suffix = "",
  className = "",
}: PnlTextProps) {
  const isPositive = value > 0;
  const isZero = value === 0;
  const prefix = isPositive ? "+" : "";
  const color = isZero
    ? "text-gray-400"
    : isPositive
      ? "text-profit"
      : "text-loss";

  const formatted =
    suffix === "%"
      ? `${prefix}${value.toFixed(2)}%`
      : suffix === "$"
        ? `${prefix}$${Math.abs(value).toFixed(2)}`
        : `${prefix}${value.toFixed(2)}`;

  // For dollar with negative, show -$X.XX
  const display =
    suffix === "$" && value < 0
      ? `-$${Math.abs(value).toFixed(2)}`
      : formatted;

  return (
    <span className={`font-medium tabular-nums ${color} ${className}`}>
      {display}
    </span>
  );
}
