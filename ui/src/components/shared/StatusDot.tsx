"use client";

const DOT_COLORS: Record<string, string> = {
  green: "bg-green-400",
  red: "bg-red-400",
  yellow: "bg-yellow-400",
  gray: "bg-gray-500",
};

interface StatusDotProps {
  color: "green" | "red" | "yellow" | "gray";
  pulse?: boolean;
  className?: string;
}

export default function StatusDot({
  color,
  pulse = false,
  className = "",
}: StatusDotProps) {
  return (
    <span
      className={`
        inline-block w-2 h-2 rounded-full
        ${DOT_COLORS[color]}
        ${pulse ? "animate-pulse-dot" : ""}
        ${className}
      `}
    />
  );
}
