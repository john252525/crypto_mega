"use client";

import { useEffect } from "react";

export const TABS = [
  "Dashboard",
  "Leaderboard",
  "Signals",
  "Positions",
  "Strategies",
  "Explore",
  "Data",
  "Logs",
  "Control",
] as const;

export type TabName = (typeof TABS)[number];

interface TabNavProps {
  activeTab: TabName;
  onTabChange: (tab: TabName) => void;
}

export default function TabNav({ activeTab, onTabChange }: TabNavProps) {
  // Sync hash on tab change
  useEffect(() => {
    const hash = `#${activeTab.toLowerCase()}`;
    if (window.location.hash !== hash) {
      window.history.replaceState(null, "", hash);
    }
  }, [activeTab]);

  // Listen for hash changes (back/forward navigation)
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1).toLowerCase();
      const match = TABS.find((t) => t.toLowerCase() === hash);
      if (match && match !== activeTab) {
        onTabChange(match);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [activeTab, onTabChange]);

  return (
    <nav className="flex items-center gap-0 border-b border-border bg-card/40 px-2 overflow-x-auto">
      {TABS.map((tab) => {
        const isActive = tab === activeTab;
        return (
          <button
            key={tab}
            onClick={() => onTabChange(tab)}
            className={`
              relative px-3 py-2.5 text-xs font-medium transition-colors duration-150
              whitespace-nowrap
              ${
                isActive
                  ? "text-accent"
                  : "text-gray-500 hover:text-gray-300"
              }
            `}
          >
            {tab}
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent rounded-full" />
            )}
          </button>
        );
      })}
    </nav>
  );
}
