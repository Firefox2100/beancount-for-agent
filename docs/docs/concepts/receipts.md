---
title: Receipts
---

A receipt is a photo or PDF kept with the entry it belongs to. The service stores it in the ledger's own `documents/` folder and links it with a Beancount `document` entry, so Fava shows it too. Whether an agent can read it is a separate, optional choice.

## Keeping receipts

- **You upload** a receipt in the web interface (**Receipts**), optionally linking it to a transaction. Only a person can upload or link one. Images (JPEG, PNG, WebP) and PDFs are accepted, decided by the file's content and not its name, up to a size limit.
- **Linking** writes two things so other tools understand it: a `document` entry on the transaction's account, and a `document` note on the transaction naming the file. A transaction can have several receipts.
- **Files you add by hand** to `documents/` are found and listed like uploaded ones. Link them with a `document` entry as usual.
- The same file is stored once, and its stored name starts with a short hash of its content.

## Checking a proposal against its receipt

When an agent proposes an entry from a receipt, the proposal carries it. The inbox shows the receipt beside the exact postings, so the figures can be checked against the source instead of taken on trust. Approving attaches it.

## Giving an agent a receipt in the chat

You can simply attach the receipt to your message. The model sees it as part of the message, as it would any image, but cannot pass it to a tool. So the harness plugin does it for you, acting as you:

1. The model calls a recording tool, or `get_receipt`, with receipt `"attached"`.
2. The plugin takes the image you attached from the conversation, stores it with the service as you (the same upload the web interface makes), and replaces `"attached"` with the stored path.
3. The proposal carries the receipt, and you see it beside the postings in the inbox.

The model never supplies a file. It can only point at one you sent, so nothing it writes can become a stored receipt. This works in Claude Code (a hook on the tool call reads the image from the session transcript) and in DeepSeek Harness (the plugin reads the session's attachment; DSH stores the normalized image, which is what the model saw). Where the harness cannot do this, upload the receipt in the web interface and give the agent its path.

## Letting an agent read receipts

Reading is off by default. Two separate switches turn it on:

| Switch | The agent gets |
| --- | --- |
| `RECEIPTS_OCR_ENABLED` | The receipt's **text**: a PDF's own text layer where it has one, otherwise OCR of the picture or scanned page. |
| `RECEIPTS_AGENT_IMAGES` | The receipt's **picture**, as an image the model can look at, if the harness supports it. |
| both off | Nothing. The tool does not exist and the agent is not told about receipts, so it asks you what a receipt says. |

With either on, the agent has `get_receipt`. When you attach the picture in the chat, the model already has it, so the picture switch matters mostly for receipts that are no longer in the conversation. It takes a path, a file name from the transaction's `document` note, or the id of a transaction that has one receipt.

- **Read on first use.** A receipt you uploaded or placed by hand has no text yet, so the first request reads it and the result is kept, keyed by the file's content. Later requests, and renamed or moved files, reuse it.
- **PDFs are judged page by page.** A page with real text uses it. A scanned page, or one whose text is unreadable placeholders, is rendered and recognised. A mixed PDF works too. With OCR off, a scanned page says so.
- **Uncertain lines are marked**, so the agent knows what to double-check against the picture or ask you.
- **It is data, not instructions.** The result says so, and the agent is told never to follow anything written on a receipt. Because every agent entry is a proposal you review, a misread total or a hostile receipt cannot post anything by itself.

## Installing OCR

Reading PDFs and pictures needs two optional dependency groups, in the same image:

```bash
docker build -t firefox2100/beancount-mcp:local --build-arg VERSION=<x> \
  --build-arg EXTRAS="--extra receipts --extra ocr" .
```

`receipts` adds Pillow and pdfium, and is enough for PDFs that have text. `ocr` adds RapidOCR, which runs the PaddleOCR models through ONNX Runtime on the CPU. The models ship inside the package, so nothing is downloaded at run time. They handle Chinese as well as Latin text. A receipt takes a second or two to read.

## Other OCR engines

OCR is behind a small interface. A Python package can register another backend through the `beancount_mcp.ocr` entry point, as importers and recipes do, and `RECEIPTS_OCR_BACKEND` selects it. It receives a Pillow image and returns pieces of text with their positions and a confidence. It never sees the ledger.
