import { useState } from 'react'
import {
  Card,
  CardActionArea,
  CardContent,
  Grid,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Plan } from '../api/types'
import { PlanCard } from './PlanCard'

const SORT_ORDER_GAP = 1000

/**
 * Calculate a new sort_order for an item moved to a given index.
 * Uses fractional indexing: takes the midpoint between neighbors.
 */
function calculateSortOrder(plans: Plan[], toIndex: number, movedPlanId: number): number {
  const others = plans.filter((p) => p.id !== movedPlanId)
  const prev = toIndex > 0 ? (others[toIndex - 1]?.sort_order ?? 0) : null
  const next = toIndex < others.length ? (others[toIndex]?.sort_order ?? 0) : null

  if (prev === null && next === null) return SORT_ORDER_GAP
  if (prev === null) return next! - SORT_ORDER_GAP
  if (next === null) return prev + SORT_ORDER_GAP
  return Math.round((prev + next) / 2)
}

interface SortablePlanCardProps {
  plan: Plan
  selected: boolean
  onSelect: () => void
  onSave: (data: { name: string; description: string }) => void
  onDelete: () => void
  saving?: boolean
}

function SortablePlanCard({ plan, selected, onSelect, onSave, onDelete, saving }: SortablePlanCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: plan.id })

  return (
    <Grid
      ref={setNodeRef}
      size={{ xs: 12, sm: 6, md: 4 }}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
      }}
      {...attributes}
      {...listeners}
    >
      <PlanCard
        plan={plan}
        selected={selected}
        onSelect={onSelect}
        onSave={onSave}
        onDelete={onDelete}
        saving={saving}
      />
    </Grid>
  )
}

interface PlanCardsProps {
  plans: Plan[]
  selectedPlanId: number | 'new' | null
  onSelectPlan: (planId: number | 'new') => void
  onCreatePlan: (data: { name: string; description: string }) => void
  onUpdatePlan: (planId: number, data: { name: string; description: string }) => void
  onDeletePlan: (planId: number) => void
  onReorder: (planId: number, newSortOrder: number) => void
  saving?: boolean
}

export function PlanCards({
  plans,
  selectedPlanId,
  onSelectPlan,
  onCreatePlan,
  onUpdatePlan,
  onDeletePlan,
  onReorder,
  saving,
}: PlanCardsProps) {
  const [showNewForm, setShowNewForm] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return

    const oldIndex = plans.findIndex((p) => p.id === active.id)
    const newIndex = plans.findIndex((p) => p.id === over.id)
    if (oldIndex === -1 || newIndex === -1) return

    const newSortOrder = calculateSortOrder(plans, newIndex, active.id as number)
    onReorder(active.id as number, newSortOrder)
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={plans.map((p) => p.id)} strategy={horizontalListSortingStrategy}>
        <Grid container spacing={2} alignItems="stretch">
          {plans.map((plan) => (
            <SortablePlanCard
              key={plan.id}
              plan={plan}
              selected={selectedPlanId === plan.id}
              onSelect={() => onSelectPlan(plan.id)}
              onSave={(data) => onUpdatePlan(plan.id, data)}
              onDelete={() => onDeletePlan(plan.id)}
              saving={saving}
            />
          ))}
          <Grid size={{ xs: 12, sm: 6, md: 4 }}>
            {showNewForm || selectedPlanId === 'new' ? (
              <PlanCard
                onSave={(data) => {
                  onCreatePlan(data)
                  setShowNewForm(false)
                }}
                onCancel={() => {
                  setShowNewForm(false)
                  onSelectPlan(plans.length > 0 ? plans[0].id : 'new')
                }}
                saving={saving}
              />
            ) : (
              <Card
                sx={{
                  height: '100%',
                  border: '2px dashed',
                  borderColor: 'divider',
                }}
              >
                <CardActionArea
                  onClick={() => {
                    setShowNewForm(true)
                    onSelectPlan('new')
                  }}
                  sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minHeight: 160,
                  }}
                >
                  <CardContent sx={{ textAlign: 'center' }}>
                    <AddIcon sx={{ fontSize: 40, color: 'action.active', mb: 1 }} />
                    <Typography variant="subtitle2" color="text.secondary">
                      New plan
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            )}
          </Grid>
        </Grid>
      </SortableContext>
    </DndContext>
  )
}
