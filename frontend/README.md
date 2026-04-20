# ValueInvesting Frontend

Next.js 15 + React 19 + TypeScript + Tailwind CSS 4。

## 启动

```bash
cd frontend
cp .env.example .env.local    # 如需调整后端地址
npm install
npm run dev                    # 启动在 http://localhost:8420
```

首页会调用后端 `/health`，确认后端已在 http://localhost:8421 运行。

## 目录

```
app/                  Next.js App Router 页面
components/
  ui/                 shadcn/ui 组件（通过 npx shadcn@latest add xxx 添加）
lib/
  utils.ts            cn() 等工具
types/                共享类型
```

## 后续添加 shadcn 组件

```bash
npx shadcn@latest add button card table dialog
```
