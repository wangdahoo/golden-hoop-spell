/**
 * ask_user - ghs 自带交互提问扩展（pi 宿主）。
 *
 * 经 pi.registerTool 注册名为 ask_user 的 LLM 可调用工具，语义对齐 Claude 侧
 * AskUserQuestion：单轮批量多题（1..4）、每题选项枚举（2..4）、推荐项标注、
 * 选项末位固定追加 Other 供自由作答。由仓库根 package.json 的 pi.extensions
 * 声明随插件分发，pi 经 jiti 直接加载本 .ts（零 npm 依赖、零构建步骤）。
 *
 * 渲染（见 plugin/shared/references/pi-host.md 块 4）：每题经 ctx.ui.select 渲染
 * label 列表，recommended 项置顶并加 "[recommended] " 前缀（select 为字符串列表
 * API，option description 不进对话框，必要上下文由 question 文本自含）；选中
 * Other 时经 ctx.ui.input 收 free-form 文本；多题按序逐题渲染，保持单轮批量语义。
 *
 * 成功返回单行 JSON {"answers":[{"question":...,"answer":...}]}；UI 不可用、
 * 参数越界（questions 非空且不超过 4 题 / options 非空且 2..4 项 / recommended
 * 不在 options 内）或用户中途取消时返回英文错误文本，不抛未捕获异常。扩展缺失
 * 或加载失败时 pi 工具表无 ask_user（pi 对扩展错误仅记录日志、会话继续），
 * pi-host.md 的文本提问条款自动接管，宿主侧零探测代码。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** 参数边界与 plan Task 9 接口一致：questions 1..4，每题 options 2..4。 */
const MAX_QUESTIONS = 4;
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 4;
const OTHER_LABEL = "Other";
const RECOMMENDED_PREFIX = "[recommended] ";

const OptionSchema = Type.Object({
	label: Type.String({ description: "Display label of the option." }),
	description: Type.Optional(
		Type.String({
			description:
				"Optional detail text. Never rendered in the dialog; keep the question text self-contained.",
		}),
	),
});

const QuestionSchema = Type.Object({
	question: Type.String({
		description: "The question text shown to the user. Must be self-contained.",
	}),
	options: Type.Array(OptionSchema, {
		description: "2 to 4 mutually exclusive options the user picks from.",
		minItems: 2,
		maxItems: 4,
	}),
	recommended: Type.Optional(
		Type.String({
			description:
				"Label of the recommended option. Pinned to the top of the list with a '[recommended] ' prefix.",
		}),
	),
});

const AskUserParams = Type.Object({
	questions: Type.Array(QuestionSchema, {
		description:
			"1 to 4 questions asked as one single-turn batch and rendered in order.",
		minItems: 1,
		maxItems: 4,
	}),
});

interface AskUserOption {
	label: string;
	description?: string;
}

interface AskUserQuestion {
	question: string;
	options: AskUserOption[];
	recommended?: string;
}

interface AnswerEntry {
	question: string;
	answer: string;
}

interface AskUserDetails {
	answers: AnswerEntry[];
	cancelled: boolean;
}

/** 构造英文错误文本的工具结果；不抛异常，由 pi 作为普通工具结果回传 LLM。 */
function errorResult(message: string): {
	content: { type: "text"; text: string }[];
	details: AskUserDetails;
} {
	return {
		content: [{ type: "text", text: message }],
		details: { answers: [], cancelled: true },
	};
}

/** 参数越界校验；全部通过返回 null，否则返回英文错误文本。 */
function validateQuestions(questions: AskUserQuestion[]): string | null {
	if (!Array.isArray(questions) || questions.length < 1 || questions.length > MAX_QUESTIONS) {
		const got = Array.isArray(questions) ? String(questions.length) : typeof questions;
		return `Error: questions must be an array of 1 to ${MAX_QUESTIONS} items, got ${got}.`;
	}
	for (const q of questions) {
		if (!q || typeof q.question !== "string" || q.question.trim() === "") {
			return "Error: every question needs a non-empty 'question' string.";
		}
		if (
			!Array.isArray(q.options) ||
			q.options.length < MIN_OPTIONS ||
			q.options.length > MAX_OPTIONS
		) {
			const got = Array.isArray(q.options) ? String(q.options.length) : typeof q.options;
			return `Error: question "${q.question}" needs ${MIN_OPTIONS} to ${MAX_OPTIONS} options, got ${got}.`;
		}
		for (const option of q.options) {
			if (!option || typeof option.label !== "string" || option.label.trim() === "") {
				return `Error: question "${q.question}" has an option without a non-empty 'label' string.`;
			}
		}
		if (q.recommended !== undefined && !q.options.some((o) => o.label === q.recommended)) {
			return `Error: question "${q.question}" recommends "${q.recommended}", which is not one of its option labels.`;
		}
	}
	return null;
}

export default function askUserExtension(pi: ExtensionAPI) {
	pi.registerTool({
		name: "ask_user",
		label: "Ask User",
		description:
			"Ask the user one or more questions as a single-turn batch (1-4 questions, each with 2-4 enumerated options). " +
			"Each question opens a select dialog with the recommended option pinned first and an 'Other' entry for a free-form answer. " +
			"Use it whenever a decision needs explicit user input before proceeding. Ask only from the main conversation, never through subagents.",
		parameters: AskUserParams,
		executionMode: "sequential",

		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			// print/json 模式下 UI 方法为 no-op（ctx.hasUI 为 false），显式报错让
			// 调用方按 pi-host.md 块 4 落回文本提问条款。
			if (!ctx.hasUI) {
				return errorResult(
					"Error: ask_user requires an interactive UI (ctx.hasUI is false, e.g. print or json mode). Ask the user in plain text instead.",
				);
			}

			const questions = params?.questions as AskUserQuestion[] | undefined;
			const invalid = validateQuestions(questions ?? []);
			if (invalid !== null) {
				return errorResult(invalid);
			}

			const answers: AnswerEntry[] = [];
			// 多题按序逐题渲染（单轮批量语义保持）；任一题被取消即整体中止，
			// 不返回部分答案，避免调用方误读批量语义。
			for (const q of questions as AskUserQuestion[]) {
				// 推荐项置顶并加前缀；其余保持原顺序；选项末位固定追加 Other。
				const ordered = q.options.map((o) => o.label);
				if (q.recommended !== undefined) {
					ordered.splice(ordered.indexOf(q.recommended), 1);
					ordered.unshift(`${RECOMMENDED_PREFIX}${q.recommended}`);
				}
				ordered.push(OTHER_LABEL);

				const choice = await ctx.ui.select(q.question, ordered);
				if (choice === undefined) {
					return errorResult(
						`Error: the user dismissed the dialog before answering "${q.question}". Ask in plain text or proceed with your recommended option.`,
					);
				}

				if (choice === OTHER_LABEL) {
					// Other 项经 ctx.ui.input 收 free-form 文本（对齐 Claude 侧 free-form 亦支持）。
					const freeForm = await ctx.ui.input(q.question, "Type your answer...");
					if (freeForm === undefined || freeForm.trim() === "") {
						return errorResult(
							`Error: the user dismissed the free-form input for "${q.question}". Ask in plain text or proceed with your recommended option.`,
						);
					}
					answers.push({ question: q.question, answer: freeForm.trim() });
					continue;
				}

				// 去掉推荐前缀，回传原始 label。
				const answer = choice.startsWith(RECOMMENDED_PREFIX)
					? choice.slice(RECOMMENDED_PREFIX.length)
					: choice;
				answers.push({ question: q.question, answer });
			}

			// 单行 JSON；answers 结构对齐 Claude 侧 AskUserQuestion。
			return {
				content: [{ type: "text", text: JSON.stringify({ answers }) }],
				details: { answers, cancelled: false } satisfies AskUserDetails,
			};
		},
	});
}
