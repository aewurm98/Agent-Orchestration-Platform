import { useSocket } from "./useSocket";

export function useGameState() {
  const { gameState, isRunning } = useSocket();

  const getRoleColor = (role: string) => {
    switch (role.toLowerCase()) {
      case "warehouse":
        return "#14120e"; // cyan
      case "distributor":
        return "#b45309"; // amber
      case "retailer":
        return "#15803d"; // green
      case "supplier":
        return "#dc2626"; // red
      default:
        return "#14120e"; // text primary
    }
  };

  return {
    gameState,
    isRunning,
    getRoleColor,
  };
}
