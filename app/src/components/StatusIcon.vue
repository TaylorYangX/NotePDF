<script setup lang="ts">
import { CircleAlert, CircleCheck, CircleDashed, CircleX, TriangleAlert } from '@lucide/vue'
import type { Status } from '../api'

defineProps<{ status: Status | 'pending' }>()
</script>

<template>
  <CircleCheck v-if="status === 'found'" class="h-4 w-4 shrink-0 text-emerald-500" :aria-label="$t('status.found')" />
  <TriangleAlert v-else-if="status === 'warning'" class="h-4 w-4 shrink-0 text-amber-500" :aria-label="$t('status.warning')" />
  <CircleAlert v-else-if="status === 'missing'" class="h-4 w-4 shrink-0 text-red-500" :aria-label="$t('status.missing')" />
  <CircleX v-else-if="status === 'invalid'" class="h-4 w-4 shrink-0 text-red-500" :aria-label="$t('status.invalid')" />
  <CircleDashed v-else class="h-4 w-4 shrink-0 animate-pulse text-zinc-400" :aria-label="$t('status.pending')" />
</template>
