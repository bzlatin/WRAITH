export declare class Context {
  scenarioId: string;
  metadata: Record<string, unknown>;
  tool(name: string, argumentsValue?: unknown, result?: unknown, success?: boolean): void;
  retrieval(source: string, documentId?: string, metadata?: Record<string, unknown>): void;
  usage(inputTokens: number, outputTokens: number): void;
  modelCall<T>(call: () => Promise<T>): Promise<T>;
}
