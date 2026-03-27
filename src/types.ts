export type Stage = '需求拆解' | '验证中' | '试运行(MVP)' | '正式上线(PROD)'
export type StatusColor = 'green' | 'amber' | 'red'
export type OperationStatus = '进行中' | '待启动' | '已暂停' | '已废弃'
export type ConditionStatus = 'pending' | 'active' | 'done' | 'blocked'
export type TaskStatus = 'pending' | 'active' | 'blocked' | 'done'

export type Project = {
  id: string
  name: string
  captain: string
  sponsor: string
  stage: Stage
  targetStage: Stage
  status: StatusColor
  operationStatus: OperationStatus
  currentFocus: string
  blocker: string
  latestFeedback: string
  feedbackFrom: string
  nextCheckpoint: string
  upgradeGap: number
  canUpgrade: string
  githubProject: string
  githubRepo: string
  wau: number
  weeklyRuns: number
  hoursSaved: number
  deliveryScore: number
  qualityScore: number
  opsScore: number
  adoptionScore: number
}

export type Condition = {
  id: string
  projectId: string
  name: string
  category: string
  fromStage: Stage
  toStage: Stage
  status: ConditionStatus
  owner: string
  criteria: string
  issue: string
  dueDate: string   // ISO date string "2025-04-30" or ""
}

export type Task = {
  id: string
  projectId: string
  conditionId: string
  title: string
  type: string
  status: TaskStatus
  assignee: string
  url: string
}

export type AppData = {
  projects: Project[]
  conditions: Condition[]
  tasks: Task[]
}
