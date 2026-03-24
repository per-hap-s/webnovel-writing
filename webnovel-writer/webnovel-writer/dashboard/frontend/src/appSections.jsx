import { TaskCenterPageSection as TaskCenterPageSectionImpl } from './taskCenterPageSection.jsx'
import { buildVisibleTaskCenterTasks } from './taskCenterVisibleTasks.js'
import { ErrorNotice } from './sectionCommon.jsx'

export { ErrorNotice } from './sectionCommon.jsx'
export { ApiSettingsSection } from './apiSettingsSection.jsx'
export { DataPageSection } from './dataPageSection.jsx'
export { FilesPageSection } from './filesPageSection.jsx'
export { PlanningProfileSection } from './planningProfileSection.jsx'
export { ProjectBootstrapSection } from './projectBootstrapSection.jsx'
export { QualityPageSection } from './qualityPageSection.jsx'
export { TaskLauncherSection } from './taskLauncherSection.jsx'

export function TaskCenterPageSection({
    tasks,
    rawTasks,
    selectedTask,
    selectedTaskId,
    currentProjectRoot,
    onSelectTask,
    onMutated,
    onNavigateOverview,
    MetricCard,
    translateTaskType,
    translateTaskStatus,
    translateStepName,
    translateEventLevel,
    translateEventMessage,
    resolveTaskStatusLabel,
    resolveCurrentStepLabel,
    resolveApprovalStatusLabel,
    resolveTargetLabel,
}) {
    const effectiveRawTasks = rawTasks || tasks
    const visibleTasks = rawTasks ? tasks : buildVisibleTaskCenterTasks(tasks)

    return (
        <TaskCenterPageSectionImpl
            tasks={visibleTasks}
            rawTasks={effectiveRawTasks}
            selectedTask={selectedTask}
            selectedTaskId={selectedTaskId}
            currentProjectRoot={currentProjectRoot}
            onSelectTask={onSelectTask}
            onMutated={onMutated}
            onNavigateOverview={onNavigateOverview}
            ErrorNotice={ErrorNotice}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
            resolveTaskStatusLabel={resolveTaskStatusLabel}
            resolveCurrentStepLabel={resolveCurrentStepLabel}
            resolveApprovalStatusLabel={resolveApprovalStatusLabel}
            resolveTargetLabel={resolveTargetLabel}
        />
    )
}
