// Single place for personal links and the API URL.
const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8050").replace(/\/+$/, "");

export const site = {
  productName: "Workflow Runner",
  tagline: "Multi-step AI workflows you can watch and approve.",
  author: "Pooya Nikbakht",
  githubUrl: "https://github.com/PooyaNikbakht",
  /** Empty hides the code links. */
  repoUrl: "https://github.com/PooyaNikbakht/workflow-runner" as string,
  portfolioUrl: "https://pooya.website",
  /** The FastAPI backend. Inlined into the browser bundle at build time. */
  apiUrl,
} as const;
