export interface VlogkitBridge {
  apiPort: number;
  token: string;
}

export interface VlogkitIPC {
  openFolder: () => Promise<string | null>;
  saveFile: (opts: {
    defaultName: string;
    filters?: { name: string; extensions: string[] }[];
  }) => Promise<string | null>;
}
