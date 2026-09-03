import { appendFile, cp, mkdir, readFile, rm } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import {
	EXTENSION_API_VERSION,
	type ExtensionContext,
	type ExtensionDefinition,
} from "../../../../packages/widi/apps/widi/src/core/extension/api.ts";

const RUN_EVENT = "e06-execution-prefix:run";
const ARM_BY_ID: Record<Arm, true> = { a0: true, a1: true, a2: true };
const CASE_ID = /^[a-z]+(?:-[a-z]+)*-\d+$/;

const DYNAMIC_CASE_PROMPT = [
	"Read and understand procedure/SKILL.md first.",
	"Then process the prepared fixture using only input/ and write output/agent_judgment.json.",
	"Follow the procedure completely, including applying and validating the judgment.",
].join(" ");

const CASE_PROMPT = [
	"Process the prepared fixture using the working guideline you have already been given.",
	"Use only input/ and write output/agent_judgment.json.",
	"Follow the procedure completely, including applying and validating the judgment.",
].join(" ");

const BOOTSTRAP_PROMPT = [
	"Read and understand procedure/SKILL.md as the working guideline for later fixture tasks.",
	"Do not read input/, inspect a fixture, or produce a judgment yet.",
	"Reply only when you are ready to apply that guideline.",
].join(" ");

type Arm = "a0" | "a1" | "a2";

type A2Resume = { sessionRef: string; bootstrapLeafId: string };

type RunPlan = {
	runId: string;
	arm: Arm;
	fixtureRoot: string;
	runRoot: string;
	skillPath: string;
	caseIds: readonly string[];
	a2Resume?: A2Resume;
};

type JsonRecord = Record<string, unknown>;

function requireRecord(value: unknown, label: string): JsonRecord {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new Error(`${label} must be a JSON object`);
	}
	return value as JsonRecord;
}

function requireString(record: JsonRecord, key: string): string {
	const value = record[key];
	if (typeof value !== "string" || value.trim() === "") throw new Error(`run plan requires ${key}`);
	return value;
}

function requireOptionalString(record: JsonRecord, key: string): string | undefined {
	const value = record[key];
	if (value === undefined) return undefined;
	if (typeof value !== "string" || value.trim() === "") throw new Error(`run plan ${key} must be a non-empty string`);
	return value;
}

function requireA2Resume(record: JsonRecord, arm: Arm): A2Resume | undefined {
	const sessionRef = requireOptionalString(record, "resume_session_ref");
	const bootstrapLeafId = requireOptionalString(record, "bootstrap_leaf_id");
	if (sessionRef === undefined && bootstrapLeafId === undefined) return undefined;
	if (sessionRef === undefined || bootstrapLeafId === undefined) {
		throw new Error("run plan must provide resume_session_ref and bootstrap_leaf_id together");
	}
	if (arm !== "a2") throw new Error("only A2 run plans may resume a shared root");
	return { sessionRef, bootstrapLeafId };
}

function requireAbsolutePath(record: JsonRecord, key: string): string {
	const value = requireString(record, key);
	if (!isAbsolute(value)) throw new Error(`run plan ${key} must be absolute`);
	return resolve(value);
}

function requireCaseIds(record: JsonRecord): readonly string[] {
	const value = record.case_ids;
	if (
		!Array.isArray(value) ||
		value.length === 0 ||
		value.some((item) => typeof item !== "string" || !CASE_ID.test(item))
	) {
		throw new Error("run plan case_ids must be a non-empty list of E06 case ids");
	}
	if (new Set(value).size !== value.length) throw new Error("run plan case_ids must not repeat a case");
	return value;
}

function configuredArm(): Arm {
	const arm = process.env.E06_ARM;
	if (arm === undefined || !(arm in ARM_BY_ID)) throw new Error("E06_ARM must be one of a0, a1, or a2");
	return arm as Arm;
}

async function loadPlan(payload: unknown, arm: Arm): Promise<RunPlan> {
	const event = requireRecord(payload, "run event payload");
	const planPath = requireString(event, "plan_path");
	if (!isAbsolute(planPath)) throw new Error("run event plan_path must be absolute");
	const plan = requireRecord(JSON.parse(await readFile(planPath, "utf-8")), "run plan");
	if (plan.schema_version !== 1) throw new Error("run plan schema_version must be 1");
	if (requireString(plan, "arm") !== arm) throw new Error(`run plan arm must match E06_ARM (${arm})`);
	return {
		runId: requireString(plan, "run_id"),
		arm,
		fixtureRoot: requireAbsolutePath(plan, "fixture_root"),
		runRoot: requireAbsolutePath(plan, "run_root"),
		skillPath: requireAbsolutePath(plan, "skill_path"),
		caseIds: requireCaseIds(plan),
		a2Resume: requireA2Resume(plan, arm),
	};
}

function activeRoot(plan: RunPlan): string {
	return resolve(plan.runRoot, "active");
}

async function record(plan: RunPlan, type: string, data: JsonRecord): Promise<void> {
	await mkdir(plan.runRoot, { recursive: true });
	await appendFile(
		resolve(plan.runRoot, "run-manifest.jsonl"),
		`${JSON.stringify({ type, at: new Date().toISOString(), run_id: plan.runId, arm: plan.arm, ...data })}\n`,
		"utf-8",
	);
}

async function prepareBootstrap(plan: RunPlan): Promise<void> {
	const active = activeRoot(plan);
	await rm(resolve(active, "input"), { recursive: true, force: true });
	await rm(resolve(active, "output"), { recursive: true, force: true });
	await rm(resolve(active, "procedure"), { recursive: true, force: true });
	await mkdir(resolve(active, "procedure"), { recursive: true });
	await mkdir(resolve(active, "output"), { recursive: true });
	await cp(plan.skillPath, resolve(active, "procedure", "SKILL.md"));
}

async function prepareCase(plan: RunPlan, caseId: string): Promise<void> {
	const active = activeRoot(plan);
	const fixture = resolve(plan.fixtureRoot, caseId);
	await rm(resolve(active, "input"), { recursive: true, force: true });
	await rm(resolve(active, "output"), { recursive: true, force: true });
	await rm(resolve(active, "procedure"), { recursive: true, force: true });
	await mkdir(active, { recursive: true });
	await cp(resolve(fixture, "input"), resolve(active, "input"), { recursive: true, errorOnExist: true });
	await mkdir(resolve(active, "output"), { recursive: true });
	await mkdir(resolve(active, "procedure"), { recursive: true });
	await cp(plan.skillPath, resolve(active, "procedure", "SKILL.md"));
}

async function archiveCase(plan: RunPlan, caseId: string): Promise<void> {
	const destination = resolve(plan.runRoot, "cases", caseId, "output");
	await mkdir(resolve(plan.runRoot, "cases", caseId), { recursive: true });
	await cp(resolve(activeRoot(plan), "output"), destination, { recursive: true, errorOnExist: true });
}

function promptOptions(target?: string): { target?: string; render: (body: string) => string } {
	return { ...(target === undefined ? undefined : { target }), render: (body) => body };
}

async function runFreshCase(plan: RunPlan, caseId: string, context: ExtensionContext): Promise<void> {
	await prepareCase(plan, caseId);
	const agentId = await context.actions.spawnAgent({ origin: { kind: "new", profileId: context.profileId } });
	try {
		const outcome = await context.actions.prompt(
			plan.arm === "a0" ? DYNAMIC_CASE_PROMPT : CASE_PROMPT,
			promptOptions(agentId),
		);
		if (outcome.kind !== "completed")
			throw new Error(`case ${caseId} was blocked: ${outcome.reason ?? "unspecified reason"}`);
		await archiveCase(plan, caseId);
		await record(plan, "case_completed", { case_id: caseId, agent_id: agentId, outcome });
	} catch (error) {
		await record(plan, "case_failed", { case_id: caseId, agent_id: agentId, error: String(error) });
		throw error;
	} finally {
		await context.actions.disposeAgent(agentId, { scope: "subtree", reason: "E06 case completed" });
	}
}

async function establishA2Bootstrap(plan: RunPlan, context: ExtensionContext): Promise<string> {
	if (plan.a2Resume !== undefined) {
		const snapshot = await context.session.getSnapshot();
		if (snapshot.leafId !== plan.a2Resume.bootstrapLeafId) {
			throw new Error("resumed A2 session is not at run plan bootstrap_leaf_id");
		}
		await record(plan, "bootstrap_resumed", {
			agent_id: context.agentId,
			resume_session_ref: plan.a2Resume.sessionRef,
			leaf_id: snapshot.leafId,
		});
		return snapshot.leafId;
	}

	await prepareBootstrap(plan);
	const bootstrap = await context.actions.prompt(BOOTSTRAP_PROMPT, promptOptions());
	const snapshot = await context.session.getSnapshot();
	if (bootstrap.kind !== "completed" || snapshot.leafId === null) {
		throw new Error("A2 bootstrap did not complete with a persisted reusable leaf");
	}
	await record(plan, "bootstrap_completed", {
		agent_id: context.agentId,
		leaf_id: snapshot.leafId,
		outcome: bootstrap,
	});
	return snapshot.leafId;
}

async function runA2(plan: RunPlan, context: ExtensionContext): Promise<void> {
	const bootstrapLeafId = await establishA2Bootstrap(plan, context);
	for (const caseId of plan.caseIds) {
		await prepareCase(plan, caseId);
		try {
			const outcome = await context.actions.prompt(CASE_PROMPT, promptOptions());
			if (outcome.kind !== "completed")
				throw new Error(`case ${caseId} was blocked: ${outcome.reason ?? "unspecified reason"}`);
			await archiveCase(plan, caseId);
			await record(plan, "case_completed", { case_id: caseId, agent_id: context.agentId, outcome });
		} catch (error) {
			await record(plan, "case_failed", { case_id: caseId, agent_id: context.agentId, error: String(error) });
			throw error;
		}
		await context.actions.navigateTree(bootstrapLeafId);
		await record(plan, "case_rewound", { case_id: caseId, leaf_id: bootstrapLeafId });
	}
}

async function runPlan(plan: RunPlan, context: ExtensionContext): Promise<void> {
	await record(plan, "run_started", { case_ids: plan.caseIds });
	try {
		if (plan.arm === "a2") {
			await runA2(plan, context);
		} else {
			for (const caseId of plan.caseIds) await runFreshCase(plan, caseId, context);
		}
		await record(plan, "run_completed", {});
		await context.actions.emitExtensionEvent("e06-execution-prefix:completed", {
			run_id: plan.runId,
			arm: plan.arm,
			case_count: plan.caseIds.length,
		});
	} catch (error) {
		await record(plan, "run_failed", { error: String(error) });
		await context.actions.emitExtensionEvent("e06-execution-prefix:failed", {
			run_id: plan.runId,
			arm: plan.arm,
			error: String(error),
		});
		throw error;
	}
}

async function appendStaticKnowledge(api: { appendSystemPrompt(text: string): void }): Promise<void> {
	const path = process.env.E06_STATIC_KNOWLEDGE;
	if (path === undefined || !isAbsolute(path)) throw new Error("A1 requires an absolute E06_STATIC_KNOWLEDGE path");
	const text = await readFile(path, "utf-8");
	if (text.trim() === "") throw new Error("E06_STATIC_KNOWLEDGE must not be empty");
	api.appendSystemPrompt(text);
}

const extension: ExtensionDefinition = {
	apiVersion: EXTENSION_API_VERSION,
	async activate(api) {
		const arm = configuredArm();
		if (arm === "a1") await appendStaticKnowledge(api);
		api.onExtensionEvent(RUN_EVENT, async (event, context) => {
			if (event.sourceAgentId !== context.agentId) return;
			let plan: RunPlan;
			try {
				plan = await loadPlan(event.payload, arm);
			} catch (error) {
				await context.actions.emitExtensionEvent("e06-execution-prefix:failed", { arm, error: String(error) });
				throw error;
			}
			await runPlan(plan, context);
		});
	},
};

export default extension;
