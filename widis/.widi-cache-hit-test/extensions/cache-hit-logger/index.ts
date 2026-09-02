import type { AgentHarnessEvent, AgentMessage } from "@arcadialin/agent-core";
import type {
	EXTENSION_API_VERSION,
	ExtensionDefinition,
} from "../../../../packages/widi/apps/widi/src/core/extension/api.ts";
import type {
	ExtensionContext,
	ExtensionObservedEventFor,
} from "../../../../packages/widi/apps/widi/src/core/extension/types.ts";

type AssistantAgentMessage = Extract<AgentMessage, { role: "assistant" }>;

interface AssistantMessageWriteEvent {
	type: "session_write";
	entryId: string;
	write: { type: "message"; message: AssistantAgentMessage };
}

function isAssistantMessageWrite(event: AgentHarnessEvent): event is AssistantMessageWriteEvent {
	if (event.type !== "session_write") return false;
	if (event.write.type !== "message") return false;
	if (event.write.message.role !== "assistant") return false;
	const usage = event.write.message.usage;
	if (!usage) return false;
	return typeof usage.cacheRead === "number" && typeof usage.cacheWrite === "number" && typeof usage.input === "number";
}

async function logCacheHitRatio(
	event: ExtensionObservedEventFor<"agent_harness_event">,
	context: ExtensionContext,
): Promise<void> {
	if (event.type !== "agent_harness_event") return;
	const harnessEvent = event.event;
	if (!isAssistantMessageWrite(harnessEvent)) return;

	const usage = harnessEvent.write.message.usage;
	const promptTokens = usage.cacheRead + usage.input + usage.cacheWrite;
	const ratio = promptTokens > 0 ? usage.cacheRead / promptTokens : 0;
	const model = context.actions.getModel();

	const record = {
		entryId: harnessEvent.entryId,
		ratio,
		cacheRead: usage.cacheRead,
		cacheWrite: usage.cacheWrite,
		input: usage.input,
		promptTokens,
		model: `${model.provider}/${model.id}`,
		recordedAt: new Date().toISOString(),
	};

	await context.session.appendEntry("cache_hit_ratio", record);
	await context.actions.reportDiagnostic({
		severity: "warning",
		code: "assistant_usage_recorded",
		message: `[cache-hit-logger] cacheRead=${usage.cacheRead} input=${usage.input} cacheWrite=${usage.cacheWrite} ratio=${ratio.toFixed(4)}`,
	});
}

const extension: ExtensionDefinition = {
	apiVersion: 1 satisfies typeof EXTENSION_API_VERSION,
	activate(api) {
		api.observe("agent_harness_event", logCacheHitRatio);
	},
};

export default extension;
