import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import Arena from "@/pages/Arena";
import Reference from "@/pages/Reference";
import Landing from "@/pages/Landing";
import { SocketProvider } from "@/context/SocketContext";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      {/* Landing is the default; the Arena lives at /arena. */}
      <Route path="/" component={Landing} />
      <Route path="/arena" component={Arena} />
      <Route path="/docs" component={Reference} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <SocketProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <Router />
          </WouterRouter>
          <Toaster />
        </SocketProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
