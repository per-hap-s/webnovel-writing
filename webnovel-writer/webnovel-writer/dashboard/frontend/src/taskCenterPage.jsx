import { useMemo } from 'react'
import {
    MetricCard,
    resolveApprovalStatusLabel,
    resolveCurrentStepLabel,
    resolveTaskStatusLabel,
    resolveTaskTargetLabel,
    translateEventLevel,
    translateEventMessage,
    translateStepName,
    translateTaskStatus,
    translateTaskType,
} from './dashboardPageCommon.jsx'
import { TaskCenterPageSection } from './appSections.jsx'
import { buildVisibleTaskCenterTasks } from './taskCenterVisibleTasks.js'

export function TaskCenterPage({ tasks, selectedTask, selectedTaskId, currentProjectRoot, onSelectTask, onMutated, onNavigateOverview }) {
    const visibleTasks = useMemo(() => buildVisibleTaskCenterTasks(tasks), [tasks])

    return (
        <TaskCenterPageSection
            tasks={visibleTasks}
            rawTasks={tasks}
            selectedTask={selectedTask}
            selectedTaskId={selectedTaskId}
            currentProjectRoot={currentProjectRoot}
            onSelectTask={onSelectTask}
            onMutated={onMutated}
            onNavigateOverview={onNavigateOverview}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
            resolveTaskStatusLabel={resolveTaskStatusLabel}
            resolveCurrentStepLabel={resolveCurrentStepLabel}
            resolveApprovalStatusLabel={resolveApprovalStatusLabel}
            resolveTargetLabel={resolveTaskTargetLabel}
        />
    )
}
