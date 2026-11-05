import { Component, type ErrorInfo, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ToastHost } from "./components/ui";
import Shell from "./components/Shell";
import Benchmarks from "./pages/Benchmarks";
import Comparison from "./pages/Comparison";
import Datasets from "./pages/Datasets";
import Observability from "./pages/Observability";
import Overview from "./pages/Overview";
import Projects from "./pages/Projects";
import Runs, { RunDetails } from "./pages/Runs";

class AppBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ReliAI page error", error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return <div className="fatal-error"><strong>This view encountered an error.</strong><p>Reload the page to try again. Your saved evaluation data is not affected.</p><button className="button button-secondary" onClick={() => window.location.reload()}>Reload view</button></div>;
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <AppBoundary>
      <Shell>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/datasets" element={<Datasets />} />
          <Route path="/datasets/:datasetId" element={<Datasets />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:runId" element={<RunDetails />} />
          <Route path="/benchmarks" element={<Benchmarks />} />
          <Route path="/benchmarks/:benchmarkId" element={<Benchmarks />} />
          <Route path="/observability" element={<Observability />} />
          <Route path="/compare" element={<Comparison />} />
          <Route path="/regressions" element={<Comparison regressionMode />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
      <ToastHost />
    </AppBoundary>
  );
}
