export {};
declare global { interface Window { atlas: { invoke(channel: string, input?: unknown): Promise<unknown> } } }