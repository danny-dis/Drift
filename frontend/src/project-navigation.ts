export function projectForNode<T extends { id: string }>(nodeId: string, projects: readonly T[]): T | undefined {
  if (!nodeId.startsWith("p:")) return undefined;
  return projects.find(project => project.id === nodeId.slice(2));
}
