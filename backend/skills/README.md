# Skills

此目录放**价值投资领域的可按需加载知识片段**。每个 `.md` 文件是一个 skill，agent 根据场景用 `load_skill(name)` 工具加载。

## 文件格式

```markdown
---
name: kebab-case-唯一标识
description: 一句话说 skill 是做什么的（给人看）
when_to_use: 一句话说什么场景下应该加载它（给模型看，选取逻辑看这个）
---

# Skill 标题

正文 markdown……
```

## 字段约定

- **`name`**：kebab-case / snake_case 都可，全目录唯一；作为 `load_skill(name)` 的 key
- **`description`**：人读的摘要
- **`when_to_use`**：**最重要**——模型靠这句决定要不要加载；写得越具体越好
- body：自由 markdown，加载时原样返回给模型

## 添加新 skill

1. 在本目录新建 `<name>.md`
2. 填好 frontmatter 三个字段
3. 写内容
4. 重启 backend 进程（当前没有热 reload）

## 不该放什么

- ❌ 永远适用的核心原则（margin of safety 等）——那些写在 `app/agents/value_agent.py` 的 system prompt 里
- ❌ 长文档（致股东信、年报全文）——走 RAG，不走 skill
- ❌ 运行时才能得到的数据（行情、财报数字）——那些由 provider / tool 提供
