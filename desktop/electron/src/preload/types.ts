export interface VlogkitBridge {
  apiPort: number;
  token: string;
}

export interface VlogkitIPC {
  openFolder: () => Promise<string | null>;
}
