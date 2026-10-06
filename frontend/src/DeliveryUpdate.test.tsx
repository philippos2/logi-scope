import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import DeliveryUpdate from "./DeliveryUpdate";
import type { DeliveryReport } from "./deliveryApi";

function receipt(body: string, replayed = false) {
  const payload = JSON.parse(body) as DeliveryReport;
  return new Response(JSON.stringify({ shipment_id: "SHP-UPDATE-001", event_id: 1000000,
    status: payload.status, occurred_at: payload.occurred_at, replayed }), { status: replayed ? 200 : 201 });
}
function setup(investigating = false) {
  const onBusy = vi.fn(), onQuestion = vi.fn();
  render(<DeliveryUpdate investigating={investigating} onBusy={onBusy} onQuestion={onQuestion} />);
  fireEvent.click(screen.getByText("配送状況の報告（デモ）"));
  return { onBusy, onQuestion };
}
function send() {
  fireEvent.submit(screen.getByRole("button", { name: /^(配送状況を報告|同じ報告を再送|報告中…)$/ }).closest("form")!);
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

test("duplicate sends are blocked and a valid receipt confirms the reported status", async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn(() => new Promise<Response>((r) => { resolve = r; }));
  vi.stubGlobal("fetch", fetch);
  const { onBusy } = setup();
  send(); send();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText("報告する配送状態") as HTMLSelectElement).disabled).toBe(true);
  const body = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body as string;
  await act(async () => resolve(receipt(body)));
  expect(screen.getByRole("status").textContent).toContain("配達完了の報告を受け付けました");
  expect(onBusy.mock.calls).toEqual([[true], [false]]);
});

test.each(["network", "server", "gateway", "malformed"])("uncertain %s outcome retries exactly the same payload", async (kind) => {
  const fetch = vi.fn().mockImplementationOnce(() => {
    if (kind === "network") return Promise.reject(new TypeError("Failed to fetch"));
    return Promise.resolve(new Response("{}", { status: kind === "server" ? 503 : kind === "gateway" ? 408 : 201 }));
  }).mockImplementation((_url: string, init: RequestInit) => Promise.resolve(receipt(init.body as string, true)));
  vi.stubGlobal("fetch", fetch);
  setup(); send();
  await screen.findByRole("alert");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText("報告日時（端末の現地時刻）") as HTMLInputElement).disabled).toBe(true);
  send();
  await screen.findByRole("status");
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
  expect(screen.getByRole("status").textContent).toContain("再送した報告の受付を確認");
});

test("a definite rejection permits editing and a new report uses a new key", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 409 }))
    .mockImplementation((_url: string, init: RequestInit) => Promise.resolve(receipt(init.body as string)));
  vi.stubGlobal("fetch", fetch);
  setup(); send();
  await screen.findByRole("alert");
  expect((screen.getByLabelText("報告する配送状態") as HTMLSelectElement).disabled).toBe(false);
  fireEvent.change(screen.getByLabelText("報告する配送状態"), { target: { value: "delayed" } });
  send(); await screen.findByRole("status");
  expect(JSON.parse(fetch.mock.calls[0][1].body).event_key).not.toBe(JSON.parse(fetch.mock.calls[1][1].body).event_key);
});

test("timeout retains the report and late responses cannot replace a retry", async () => {
  vi.useFakeTimers();
  const resolves: ((response: Response) => void)[] = [];
  const fetch = vi.fn(() => new Promise<Response>((r) => resolves.push(r)));
  vi.stubGlobal("fetch", fetch);
  setup(); send();
  await act(async () => vi.advanceTimersByTime(30_000));
  expect(screen.getByRole("alert").textContent).toContain("時間超過");
  send();
  const body = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body as string;
  await act(async () => resolves[0](receipt(body)));
  expect(screen.queryByRole("status")).toBeNull();
  await act(async () => resolves[1](receipt(body, true)));
  expect(screen.getByRole("status").textContent).toContain("再送した報告の受付を確認");
  expect((fetch.mock.calls[1] as unknown as [string, RequestInit])[1].body).toBe(body);
});

test("the investigation link fills the question without sending a request", () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const { onQuestion } = setup();
  fireEvent.click(screen.getByRole("button", { name: "更新用荷物を調べる" }));
  expect(onQuestion).toHaveBeenCalledWith("SHP-UPDATE-001の配送状態は？");
  expect(fetch).not.toHaveBeenCalled();
});

test("an ongoing investigation blocks update submission", async () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  setup(true); send();
  await waitFor(() => expect(fetch).not.toHaveBeenCalled());
  expect((screen.getByRole("button", { name: "配送状況を報告" }) as HTMLButtonElement).disabled).toBe(true);
});
