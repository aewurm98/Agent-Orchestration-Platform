import { useSocket } from "./useSocket";

export function useGameState() {
  const { gameState, isRunning } = useSocket();

  const getRoleColor = (role: string) => {
    switch (role.toLowerCase()) {
      case "warehouse":
        return "#00d9ff"; // cyan
      case "distributor":
        return "#f59e0b"; // amber
      case "retailer":
        return "#7ee787"; // green
      case "supplier":
        return "#ff6b6b"; // red
      default:
        return "#e6edf3"; // text primary
    }
  };

  return {
    gameState,
    isRunning,
    getRoleColor,
  };
}
