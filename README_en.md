# zuken-ai — AI-Powered Mechanical Drawing Review Tool

> **日本語 README は [こちら](../README.md)**

## What is zuken-ai?

**zuken-ai** (図検 AI) is an open-source AI tool that automatically reviews mechanical engineering drawings. Upload a drawing image (PNG/JPG) and get instant feedback on:

- **Drafting rule violations** based on JIS/ISO standards
- **Machining feasibility issues** (corner radii, tool access, deep holes, etc.)
- **Cost reduction suggestions** from a machinist's perspective (DFM/DFA)

## Who is it for?

Small machine shops (町工場) that receive drawings from customers and want to provide professional feedback: *"If you change this, we can make it faster, cheaper, and better."*

## How it works

```
Drawing image (PNG/JPG)
    ↓
Claude Vision API + 90-chunk knowledge base
    ↓
Review results (error / warning / suggestion with rule references)
```

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/zuken-ai.git
cd zuken-ai
pip install flask anthropic
export ANTHROPIC_API_KEY="sk-ant-..."   # or set on Windows
python app.py
# Open http://localhost:5000
```

## Knowledge Base

90 structured chunks across 4 layers:

| Layer | Count | Description |
|-------|-------|-------------|
| drawing_principles | 20 | JIS/ISO drafting rules |
| machining | 20 | Machining constraints & best practices |
| inspection_patterns | 20 | Common drawing review findings |
| cost_proposal | 30 | Cost reduction & DFM/DFA suggestions |

## Cost

~$0.06-0.10 per review (Claude Sonnet API).

## License

MIT License — free to use, modify, and distribute.

## Contributing

We especially welcome **machining knowledge contributions** — real-world shop floor insights that make this tool better for everyone.
