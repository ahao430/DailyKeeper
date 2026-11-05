<template>
  <template v-if="schema.length">
    <el-form-item
      v-for="field in schema"
      :key="field.name"
      :label="field.label"
      :prop="propPath(field.name)"
      :rules="rulesFor(field)"
    >
      <el-switch
        v-if="field.type === 'boolean'"
        :model-value="booleanValue(field)"
        @update:model-value="(value: string | number | boolean) => setValue(field.name, Boolean(value))"
      />
      <el-input-number
        v-else-if="field.type === 'number'"
        :model-value="numberValue(field)"
        :placeholder="field.placeholder || undefined"
        :controls-position="'right'"
        style="width: 100%"
        @update:model-value="(value: number | undefined) => setValue(field.name, value)"
      />
      <el-select
        v-else-if="field.type === 'select'"
        :model-value="stringValue(field)"
        :placeholder="field.placeholder || `请选择${field.label}`"
        clearable
        style="width: 100%"
        @update:model-value="(value: string) => setValue(field.name, value)"
      >
        <el-option
          v-for="option in optionList(field)"
          :key="optionValue(option)"
          :label="optionLabel(option)"
          :value="optionValue(option)"
        />
      </el-select>
      <el-input
        v-else-if="field.type === 'secret'"
        type="password"
        show-password
        :model-value="stringValue(field)"
        :placeholder="field.placeholder || `请输入${field.label}`"
        @update:model-value="(value: string) => setValue(field.name, value)"
      />
      <el-input
        v-else
        :model-value="stringValue(field)"
        :placeholder="field.placeholder || `请输入${field.label}`"
        @update:model-value="(value: string) => setValue(field.name, value)"
      />
      <div v-if="field.help" class="dynamic-field-help">{{ field.help }}</div>
    </el-form-item>
  </template>
</template>

<script lang="ts">
import type { FieldDef } from "../api/types";

interface OptionObject {
  label: unknown;
  value: unknown;
}

function isOptionObject(option: unknown): option is OptionObject {
  return typeof option === "object" && option !== null && ("value" in option || "label" in option);
}

/** Initial config object for a schema: falls back to each field's declared default. */
export function buildFormDefaults(schema: FieldDef[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of schema) {
    if (field.default !== undefined && field.default !== null) {
      result[field.name] = field.default;
    } else if (field.type === "boolean") {
      result[field.name] = false;
    } else {
      result[field.name] = "";
    }
  }
  return result;
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import type { FormItemRule } from "element-plus";

const props = withDefaults(
  defineProps<{
    schema: FieldDef[];
    modelValue: Record<string, unknown>;
    /** Path prefix inside the parent form model, e.g. "config" renders prop="config.xxx". */
    prefix?: string;
  }>(),
  { prefix: "" },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: Record<string, unknown>): void;
}>();

const schema = computed(() => props.schema ?? []);

function propPath(name: string): string {
  return props.prefix ? `${props.prefix}.${name}` : name;
}

function rawValue(field: FieldDef): unknown {
  const current = props.modelValue ?? {};
  return current[field.name] === undefined ? field.default : current[field.name];
}

function stringValue(field: FieldDef): string {
  const value = rawValue(field);
  return value === undefined || value === null ? "" : String(value);
}

function numberValue(field: FieldDef): number | undefined {
  const value = rawValue(field);
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function booleanValue(field: FieldDef): boolean {
  const value = rawValue(field);
  return value === undefined || value === null ? false : Boolean(value);
}

function optionList(field: FieldDef): unknown[] {
  return Array.isArray(field.options) ? field.options : [];
}

function optionLabel(option: unknown): string {
  if (isOptionObject(option)) {
    return String(option.label ?? option.value);
  }
  return String(option);
}

function optionValue(option: unknown): string {
  if (isOptionObject(option)) {
    return String(option.value ?? option.label);
  }
  return String(option);
}

function rulesFor(field: FieldDef): FormItemRule[] {
  const rules: FormItemRule[] = [];
  if (field.required) {
    rules.push({
      required: true,
      message: field.type === "select" ? `请选择${field.label}` : `请输入${field.label}`,
      trigger: field.type === "select" || field.type === "boolean" ? "change" : "blur",
    });
  }
  return rules;
}

function setValue(name: string, value: unknown): void {
  emit("update:modelValue", { ...(props.modelValue ?? {}), [name]: value });
}
</script>

<style scoped>
.dynamic-field-help {
  width: 100%;
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}
</style>
