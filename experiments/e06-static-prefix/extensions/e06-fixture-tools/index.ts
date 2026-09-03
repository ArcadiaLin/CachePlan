import { readFile, realpath, stat, writeFile } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";
import {
	EXTENSION_API_VERSION,
	type ExtensionDefinition,
} from "../../../../packages/widi/apps/widi/src/core/extension/api.ts";
import { Type } from "../../../../packages/widi/node_modules/typebox/build/index.mjs";

const CONTRACT_PATH = "input/judgment_contract.json";
const JUDGMENT_PATH = "output/agent_judgment.json";
const MAX_JUDGMENT_BYTES = 2 * 1024 * 1024;

type JsonRecord = Record<string, unknown>;
type ValidationReport = { valid: boolean; resourceCount: number; errors: string[] };

function throwIfAborted(signal: AbortSignal | undefined): void {
	if (signal?.aborted) throw new Error("Operation aborted");
}

function isInside(root: string, target: string): boolean {
	const path = relative(root, target);
	return path === "" || (!path.startsWith(`..${sep}`) && path !== ".." && !isAbsolute(path));
}

async function assertExistingPath(cwd: string, rawPath: string, allowedRoot: string): Promise<void> {
	const root = await realpath(resolve(cwd, allowedRoot));
	const target = await realpath(resolve(cwd, rawPath));
	if (!isInside(root, target)) throw new Error(`E06 fixture policy forbids access outside ${allowedRoot}: ${rawPath}`);
}

async function assertReadablePath(cwd: string, rawPath: string): Promise<void> {
	const target = resolve(cwd, rawPath);
	if (target === resolve(cwd, "procedure/SKILL.md")) return;
	await assertExistingPath(cwd, rawPath, "input");
}

async function assertJudgmentPath(cwd: string, rawPath: string): Promise<void> {
	const expected = resolve(cwd, JUDGMENT_PATH);
	const target = resolve(cwd, rawPath);
	if (target !== expected) throw new Error(`E06 fixture policy permits writes only to ${JUDGMENT_PATH}: ${rawPath}`);
	const outputRoot = await realpath(resolve(cwd, "output"));
	if (!isInside(outputRoot, target)) throw new Error(`E06 fixture policy forbids output path: ${rawPath}`);
}

function pathArgument(params: unknown, tool: string): string {
	if (typeof params !== "object" || params === null || Array.isArray(params)) {
		throw new Error(`${tool} parameters must be an object`);
	}
	const value = (params as JsonRecord).path;
	if (typeof value !== "string" || value.length === 0) throw new Error(`${tool} requires a non-empty path`);
	return value;
}

function parseJson(text: string, path: string): JsonRecord {
	let value: unknown;
	try {
		value = JSON.parse(text);
	} catch (error) {
		throw new Error(`${path} is not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
	}
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new Error(`${path} must contain a JSON object`);
	}
	return value as JsonRecord;
}

async function readBoundedJson(path: string, signal: AbortSignal | undefined): Promise<JsonRecord> {
	throwIfAborted(signal);
	const info = await stat(path);
	throwIfAborted(signal);
	if (info.size > MAX_JUDGMENT_BYTES) throw new Error(`${path} exceeds ${MAX_JUDGMENT_BYTES} bytes`);
	const text = await readFile(path, "utf-8");
	throwIfAborted(signal);
	return parseJson(text, path);
}

function sameKeys(value: JsonRecord, template: JsonRecord, location: string, errors: string[]): void {
	const actual = Object.keys(value).sort();
	const expected = Object.keys(template).sort();
	if (actual.join("\u0000") !== expected.join("\u0000")) {
		errors.push(`${location} has unexpected or missing fields`);
	}
	for (const [key, expectedValue] of Object.entries(template)) {
		const actualValue = value[key];
		const field = `${location}.${key}`;
		if (Array.isArray(expectedValue)) {
			if (!Array.isArray(actualValue)) errors.push(`${field} must be an array`);
			continue;
		}
		if (typeof expectedValue === "object" && expectedValue !== null && !Array.isArray(expectedValue)) {
			if (typeof actualValue !== "object" || actualValue === null || Array.isArray(actualValue)) {
				errors.push(`${field} must be an object`);
			} else {
				sameKeys(actualValue as JsonRecord, expectedValue as JsonRecord, field, errors);
			}
			continue;
		}
		if (typeof actualValue !== typeof expectedValue) errors.push(`${field} has the wrong value type`);
	}
}

function inEnum(value: unknown, choices: unknown): boolean {
	return Array.isArray(choices) && choices.includes(value);
}

function validateJudgment(judgment: JsonRecord, contract: JsonRecord): ValidationReport {
	const errors: string[] = [];
	const template = contract.output_template;
	const resourceTemplate = contract.resource_template;
	const enums = contract.enums;
	if (
		typeof template !== "object" ||
		template === null ||
		Array.isArray(template) ||
		typeof resourceTemplate !== "object" ||
		resourceTemplate === null ||
		Array.isArray(resourceTemplate) ||
		typeof enums !== "object" ||
		enums === null ||
		Array.isArray(enums)
	) {
		throw new Error(`${CONTRACT_PATH} has no valid output template, resource template, and enums`);
	}
	const outputTemplate = template as JsonRecord;
	const resourceShape = resourceTemplate as JsonRecord;
	const enumValues = enums as JsonRecord;
	sameKeys(judgment, outputTemplate, "agent_judgment", errors);
	const paperId = judgment.paper_id;
	if (typeof paperId !== "string" || paperId.length === 0) errors.push("paper_id must be a non-empty string");
	const paperRecord = judgment.paper_record;
	if (typeof paperRecord === "object" && paperRecord !== null && !Array.isArray(paperRecord)) {
		const record = paperRecord as JsonRecord;
		const intent = record.intent;
		if (
			typeof intent !== "object" ||
			intent === null ||
			Array.isArray(intent) ||
			!inEnum((intent as JsonRecord).paper_type, enumValues.paper_type)
		) {
			errors.push("paper_record.intent.paper_type is invalid");
		}
		const citations = record.citation_functions;
		if (!Array.isArray(citations)) {
			errors.push("paper_record.citation_functions must be an array");
		} else {
			for (const [index, citation] of citations.entries()) {
				if (
					typeof citation !== "object" ||
					citation === null ||
					Array.isArray(citation) ||
					!inEnum((citation as JsonRecord).citation_function, enumValues.citation_function)
				) {
					errors.push(`citation_functions[${index}] has an invalid citation_function`);
				}
			}
		}
	}
	const resources = judgment.resources;
	if (!Array.isArray(resources)) {
		errors.push("resources must be an array");
		return { valid: false, resourceCount: 0, errors };
	}
	for (const [index, resource] of resources.entries()) {
		if (typeof resource !== "object" || resource === null || Array.isArray(resource)) {
			errors.push(`resources[${index}] must be an object`);
			continue;
		}
		const record = resource as JsonRecord;
		sameKeys(record, resourceShape, `resources[${index}]`, errors);
		if (!inEnum(record.kind, enumValues.resource_kind)) errors.push(`resources[${index}].kind is invalid`);
		if (!inEnum(record.relation_type, enumValues.relation_type))
			errors.push(`resources[${index}].relation_type is invalid`);
		const access = record.access;
		if (
			typeof access !== "object" ||
			access === null ||
			Array.isArray(access) ||
			!inEnum((access as JsonRecord).access_type, enumValues.access_type)
		) {
			errors.push(`resources[${index}].access.access_type is invalid`);
		}
		const availability = record.availability;
		if (
			typeof availability !== "object" ||
			availability === null ||
			Array.isArray(availability) ||
			!inEnum((availability as JsonRecord).status, enumValues.availability_status)
		) {
			errors.push(`resources[${index}].availability.status is invalid`);
		}
		const callable = record.agent_callable;
		if (
			typeof callable !== "object" ||
			callable === null ||
			Array.isArray(callable) ||
			!inEnum((callable as JsonRecord).estimated_wrapping_difficulty, enumValues.wrapping_difficulty)
		) {
			errors.push(`resources[${index}].agent_callable.estimated_wrapping_difficulty is invalid`);
		}
	}
	return { valid: errors.length === 0, resourceCount: resources.length, errors };
}

async function inspectFixture(
	cwd: string,
	signal: AbortSignal | undefined,
): Promise<{ judgment: JsonRecord; report: ValidationReport }> {
	await assertExistingPath(cwd, CONTRACT_PATH, "input");
	await assertJudgmentPath(cwd, JUDGMENT_PATH);
	const contract = await readBoundedJson(resolve(cwd, CONTRACT_PATH), signal);
	const judgment = await readBoundedJson(resolve(cwd, JUDGMENT_PATH), signal);
	return { judgment, report: validateJudgment(judgment, contract) };
}

function reportText(report: ValidationReport): string {
	if (report.valid) return `Validation passed: ${report.resourceCount} resource records.`;
	const shown = report.errors.slice(0, 20);
	const suffix = report.errors.length > shown.length ? `\n… ${report.errors.length - shown.length} more errors` : "";
	return `Validation failed (${report.errors.length} errors):\n- ${shown.join("\n- ")}${suffix}`;
}

const extension: ExtensionDefinition = {
	apiVersion: EXTENSION_API_VERSION,
	activate(api) {
		api.patchTool("read", {
			aroundExecute: async (next, toolCallId, params, context) => {
				const path = pathArgument(params, "read");
				await assertReadablePath(context.workspace.cwd, path);
				return await next(toolCallId, params, context);
			},
		});
		for (const tool of ["grep", "find"] as const) {
			api.patchTool(tool, {
				aroundExecute: async (next, toolCallId, params, context) => {
					const path = pathArgument(params, tool);
					await assertExistingPath(context.workspace.cwd, path, "input");
					return await next(toolCallId, params, context);
				},
			});
		}
		api.patchTool("write", {
			aroundExecute: async (next, toolCallId, params, context) => {
				const path = pathArgument(params, "write");
				await assertJudgmentPath(context.workspace.cwd, path);
				return await next(toolCallId, params, context);
			},
		});
		api.registerTool({
			name: "p4a_apply_judgment",
			label: "Apply P4A judgment",
			description: "Validate and canonically serialize output/agent_judgment.json against the frozen fixture contract.",
			parameters: Type.Object({}),
			async execute(_toolCallId, _params, context) {
				const { judgment, report } = await inspectFixture(context.workspace.cwd, context.signal);
				if (!report.valid) throw new Error(reportText(report));
				throwIfAborted(context.signal);
				await writeFile(
					resolve(context.workspace.cwd, JUDGMENT_PATH),
					`${JSON.stringify(judgment, null, 2)}\n`,
					"utf-8",
				);
				throwIfAborted(context.signal);
				return {
					content: [{ type: "text" as const, text: `Applied judgment: ${report.resourceCount} resource records.` }],
					details: report,
				};
			},
		});
		api.registerTool({
			name: "p4a_validate_outputs",
			label: "Validate P4A outputs",
			description:
				"Validate output/agent_judgment.json against the frozen fixture contract and return bounded repair errors.",
			parameters: Type.Object({}),
			async execute(_toolCallId, _params, context) {
				const { report } = await inspectFixture(context.workspace.cwd, context.signal);
				return { content: [{ type: "text" as const, text: reportText(report) }], details: report };
			},
		});
	},
};

export default extension;
