import { useEffect, useRef, useState } from "react";
import { investigate, type AgentResponse } from "./api";
export function useInvestigation() {
  const [pending, setPending] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState<AgentResponse>();
  const [submitted, setSubmitted] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const clearTimers = useRef<(() => void) | null>(null);
  useEffect(
    () => () => {
      sequence.current++;
      clearTimers.current?.();
      active.current?.abort();
    },
    [],
  );
  async function send(question: string) {
    question = question.trim();
    if (active.current || !question || Array.from(question).length > 4000)
      return;
    const controller = new AbortController();
    active.current = controller;
    const id = ++sequence.current;
    setPending(true);
    setSeconds(0);
    setResult(undefined);
    setSubmitted(question);
    setError("");
    setNotice("調査を開始しました。");
    const started = Date.now();
    const interval = setInterval(() => {
      if (id === sequence.current)
        setSeconds(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    const timeout = setTimeout(() => {
      if (id !== sequence.current) return;
      sequence.current++;
      clearTimers.current?.();
      active.current = null;
      controller.abort();
      setPending(false);
      setNotice("");
      setError(
        "応答待ちが時間超過しました。サーバ側の調査は続いている場合があります。",
      );
    }, 960_000);
    const cleanupTimers = () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
    clearTimers.current = cleanupTimers;
    try {
      const response = await investigate(question, controller.signal);
      if (id === sequence.current) {
        setResult(response);
        setNotice("調査結果を受信しました。");
      }
    } catch (e) {
      if (id === sequence.current) {
        setNotice("");
        setError(e instanceof Error ? e.message : "通信に失敗しました。");
      }
    } finally {
      cleanupTimers();
      if (id === sequence.current) {
        active.current = null;
        setPending(false);
      }
    }
  }
  function stop() {
    sequence.current++;
    clearTimers.current?.();
    active.current?.abort();
    active.current = null;
    setPending(false);
    setNotice("待機を終了しました。サーバ側の調査は続いている場合があります。");
  }
  return { pending, seconds, result, submitted, notice, error, send, stop };
}
