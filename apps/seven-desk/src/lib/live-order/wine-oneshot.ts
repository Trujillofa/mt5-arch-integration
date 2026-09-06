import { spawn } from "node:child_process";

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Launch wine without blocking the Node event loop. Resolves when `isDone`
 * is true, the child exits, or `deadlineMs` is hit. On deadline, `onAbort`
 * must kill the Wine prefix (grandchildren ignore SIGTERM on the wrapper).
 */
export async function runWineUntil(input: {
  cwd: string;
  args: readonly string[];
  env: NodeJS.ProcessEnv;
  deadlineMs: number;
  isDone: () => boolean;
  onAbort: () => unknown;
}): Promise<{ timedOut: boolean; exitCode: number | null }> {
  const child = spawn("wine", [...input.args], {
    cwd: input.cwd,
    env: input.env,
    stdio: "ignore",
  });

  let exitCode: number | null = null;
  let spawnFailed = false;
  child.on("exit", (code) => {
    exitCode = code;
  });
  child.on("error", () => {
    spawnFailed = true;
    if (exitCode == null) exitCode = 1;
  });

  const abortChild = async (): Promise<void> => {
    try {
      child.kill("SIGTERM");
    } catch {
      // already gone
    }
    await input.onAbort();
  };

  while (Date.now() < input.deadlineMs) {
    if (input.isDone()) {
      return { timedOut: false, exitCode };
    }
    if (spawnFailed) {
      return { timedOut: false, exitCode };
    }
    if (exitCode !== null) {
      await sleep(400);
      return { timedOut: !input.isDone(), exitCode };
    }
    await sleep(250);
  }

  await abortChild();
  return { timedOut: true, exitCode };
}
