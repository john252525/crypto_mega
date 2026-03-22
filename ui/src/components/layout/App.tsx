"use client";

import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import Header from "./Header";
import TabNav, { TABS, type TabName } from "./TabNav";

// ---------------------------------------------------------------------------
// Lazy-loaded tab panels
// ---------------------------------------------------------------------------
const DashboardTab = lazy(() => import("@/components/dashboard/DashboardTab"));
const LeaderboardTab = lazy(() => import("@/components/leaderboard/LeaderboardTab"));
const SignalsTab = lazy(() => import("@/components/signals/SignalsTab"));
const PositionsTab = lazy(() => import("@/components/positions/PositionsTab"));
const StrategiesTab = lazy(() => import("@/components/strategies/StrategiesTab"));
const ExploreTab = lazy(() => import("@/components/explore/ExploreTab"));
const DataTab = lazy(() => import("@/components/data/DataTab"));
const LogsTab = lazy(() => import("@/components/logs/LogsTab"));
const ControlTab = lazy(() => import("@/components/control/ControlTab"));

const TAB_COMPONENTS: Record<TabName, React.LazyExoticComponent<() => React.JSX.Element>> = {
  Dashboard: DashboardTab,
  Leaderboard: LeaderboardTab,
  Signals: SignalsTab,
  Positions: PositionsTab,
  Strategies: StrategiesTab,
  Explore: ExploreTab,
  Data: DataTab,
  Logs: LogsTab,
  Control: ControlTab,
};

function getInitialTab(): TabName {
  if (typeof window === "undefined") return "Dashboard";
  const hash = window.location.hash.slice(1).toLowerCase();
  const match = TABS.find((t) => t.toLowerCase() === hash);
  return match ?? "Dashboard";
}

function TabFallback() {
  return (
    <div className="flex items-center justify-center h-64 text-gray-500 text-xs">
      <div className="animate-spin-slow w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full mr-2" />
      Loading...
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabName>("Dashboard");

  // Read hash on mount (client only)
  useEffect(() => {
    setActiveTab(getInitialTab());
  }, []);

  const handleTabChange = useCallback((tab: TabName) => {
    setActiveTab(tab);
  }, []);

  const ActiveComponent = TAB_COMPONENTS[activeTab];

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={handleTabChange} />
      <main className="flex-1 p-4 animate-fadeIn">
        <Suspense fallback={<TabFallback />}>
          <ActiveComponent />
        </Suspense>
      </main>
    </div>
  );
}
