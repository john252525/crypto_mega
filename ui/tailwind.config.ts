import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0a0a0f',
        card: '#12121a',
        border: '#1e1e2e',
        accent: '#00ff88',
        accentDim: '#00cc6a',
        blue: '#00bfff',
        warn: '#ff9800',
        danger: '#f44336',
        profit: '#00ff88',
        loss: '#ff4444',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
