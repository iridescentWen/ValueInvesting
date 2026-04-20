import { API_URL, fetchHealth } from "@/lib/api";

export default async function Home() {
  const health = await fetchHealth();

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-xl w-full space-y-6">
        <header>
          <h1 className="text-3xl font-bold tracking-tight">ValueInvesting</h1>
          <p className="text-neutral-500 mt-1">
            AI agent for value investing — scaffold ready.
          </p>
        </header>

        <section className="rounded-lg border border-neutral-200 dark:border-neutral-800 p-4">
          <h2 className="font-semibold mb-2">Backend health</h2>
          {health ? (
            <dl className="text-sm grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
              <dt className="text-neutral-500">status</dt>
              <dd>{health.status}</dd>
              <dt className="text-neutral-500">env</dt>
              <dd>{health.env}</dd>
              <dt className="text-neutral-500">llm_model</dt>
              <dd className="font-mono">{health.llm_model}</dd>
            </dl>
          ) : (
            <p className="text-sm text-red-600">
              无法连接后端 /health —— 确认 backend 已启动（{API_URL}）
            </p>
          )}
        </section>

        <section className="text-sm text-neutral-500">
          下一步：接入 AkShare provider + 筛选接口
        </section>
      </div>
    </main>
  );
}
