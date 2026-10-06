import { afterEach, expect, test, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
const data = {
  answer: "センサー故障による遅延です。",
  sources: [{ id: "shipment:SHP-1", kind: "shipment" }],
  steps: [
    {
      tool: "get_shipment_details",
      args: { shipment_id: "SHP-1" },
      ok: false,
      error: "timeout",
    },
  ],
  unresolved: [
    {
      code: "insufficient_evidence",
      message: "復旧予定は未確定です。",
      details: {},
    },
  ],
};
const response = (value = data) =>
  new Response(JSON.stringify(value), { status: 200 });
function enter(text = "遅延原因は？") {
  fireEvent.change(screen.getByLabelText("質問"), { target: { value: text } });
}
function send() {
  fireEvent.submit(
    screen.getByRole("button", { name: "調査する" }).closest("form")!,
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("samples populate input without sending; empty, oversized and IME submissions are blocked", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  expect(
    (screen.getByRole("button", { name: "調査する" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "多段調査" }));
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("追加データで試す質問（9問）"));
  fireEvent.click(screen.getByRole("button", { name: "営業所で特定" }));
  expect((screen.getByLabelText("質問") as HTMLTextAreaElement).value).toBe(
    "架空第12営業所のデモ銀河資材の遅延荷物は？",
  );
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.keyDown(screen.getByLabelText("質問"), {
    key: "Enter",
    ctrlKey: true,
    isComposing: true,
  });
  expect(fetch).not.toHaveBeenCalled();
  enter("あ".repeat(4001));
  send();
  expect(fetch).not.toHaveBeenCalled();
});

test("duplicate sends are blocked and partial answer, sources and failed tool remain visible", async () => {
  let resolve!: (value: Response) => void;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((r) => {
        resolve = r;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  enter();
  send();
  fireEvent.submit(
    screen.getByRole("button", { name: "調査中…" }).closest("form")!,
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => resolve(response()));
  expect(screen.getByText(data.answer)).toBeTruthy();
  expect(screen.getByText("復旧予定は未確定です。")).toBeTruthy();
  expect(screen.getByText("失敗")).toBeTruthy();
  expect(screen.getByText("shipment:SHP-1")).toBeTruthy();
});

test("busy error retains input and allows another send", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "agent_busy" } }), {
        status: 503,
      }),
    );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  enter();
  send();
  await screen.findByRole("alert");
  expect((screen.getByLabelText("質問") as HTMLTextAreaElement).value).toBe(
    "遅延原因は？",
  );
  expect(
    (screen.getByRole("button", { name: "調査する" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});

test("ending wait prevents old response overwriting a new result", async () => {
  const resolvers: ((value: Response) => void)[] = [];
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => resolvers.push(resolve)),
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  enter();
  send();
  fireEvent.click(screen.getByRole("button", { name: "待機を終了" }));
  enter("次の質問");
  send();
  await act(async () => resolvers[1](response()));
  await act(async () =>
    resolvers[0](response({ ...data, answer: "古い結果" })),
  );
  expect(screen.queryByText("古い結果")).toBeNull();
  expect(screen.getByText(data.answer)).toBeTruthy();
});

test("invalid response is shown as an error, not a successful investigation", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        response({
          ...data,
          steps: [{ tool: "bad", args: {}, ok: "yes" }],
        } as unknown as typeof data),
      ),
  );
  render(<App />);
  enter();
  send();
  await screen.findByRole("alert");
  expect(screen.queryByText(data.answer)).toBeNull();
});

test("client timeout ends waiting and ignores late response", async () => {
  vi.useFakeTimers();
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    ),
  );
  render(<App />);
  enter();
  send();
  await act(async () => vi.advanceTimersByTime(960_000));
  expect(screen.getByRole("alert").textContent).toContain("時間超過");
  await act(async () => resolve(response()));
  expect(screen.queryByText(data.answer)).toBeNull();
});

test("network failure can be retried without automatic resubmission", async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  enter();
  send();
  await screen.findByRole("alert");
  expect(fetch).toHaveBeenCalledTimes(1);
  send();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
});
