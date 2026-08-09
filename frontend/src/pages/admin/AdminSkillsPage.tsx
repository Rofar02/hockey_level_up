import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'
import * as skillsApi from '../../api/skills'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { SkillOption } from '../../types/skill'

export function AdminSkillsPage() {
  const { accessToken } = useAuth()

  const [skills, setSkills] = useState<SkillOption[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const [newName, setNewName] = useState('')
  const [newRequiredLevel, setNewRequiredLevel] = useState('1')
  const [createError, setCreateError] = useState<string | null>(null)
  const [isCreating, setIsCreating] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    skillsApi
      .listSkillsAdmin(accessToken)
      .then((result) => {
        if (!cancelled) {
          setSkills(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навыки.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setCreateError(null)
    if (newName.trim() === '') {
      setCreateError('Название обязательно.')
      return
    }
    const requiredLevel = Number(newRequiredLevel)
    if (!Number.isInteger(requiredLevel) || requiredLevel < 1) {
      setCreateError('Уровень должен быть целым числом от 1.')
      return
    }
    setIsCreating(true)
    try {
      const created = await skillsApi.createSkill(
        { name: newName.trim(), required_level: requiredLevel },
        accessToken,
      )
      setSkills((previous) => [...(previous ?? []), created])
      setNewName('')
      setNewRequiredLevel('1')
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Не удалось создать навык.')
    } finally {
      setIsCreating(false)
    }
  }

  async function handleDelete(skill: SkillOption) {
    if (accessToken === null) {
      return
    }
    if (!window.confirm(`Удалить навык «${skill.name}»?`)) {
      return
    }
    try {
      await skillsApi.deleteSkill(skill.id, accessToken)
      setSkills((previous) => previous?.filter((item) => item.id !== skill.id) ?? previous)
    } catch (err) {
      window.alert(err instanceof ApiError ? err.message : 'Не удалось удалить навык.')
    }
  }

  return (
    <AdminLayout title="Навыки">
      <form onSubmit={handleCreate} className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end">
        <TextField
          label="Новый навык"
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          maxLength={255}
          className="sm:w-64"
        />
        <TextField
          label="Требуемый уровень"
          type="number"
          numeric
          min={1}
          value={newRequiredLevel}
          onChange={(event) => setNewRequiredLevel(event.target.value)}
          className="sm:w-40"
        />
        <Button type="submit" isLoading={isCreating}>
          Добавить
        </Button>
      </form>
      <FormError message={createError} />

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && skills !== null && (
        <div className="overflow-hidden rounded-md border border-white/10">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                <th className="px-3 py-2 font-medium">Название</th>
                <th className="px-3 py-2 font-medium">Уровень</th>
                <th className="px-3 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {skills.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-text-secondary">
                    Пока нет навыков.
                  </td>
                </tr>
              )}
              {skills.map((skill) => (
                <tr key={skill.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-3 py-2 text-text-primary">{skill.name}</td>
                  <td className="px-3 py-2 font-mono text-text-secondary">{skill.required_level}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-3">
                      <Link to={`/admin/skills/${skill.id}`} className="text-accent-ice hover:underline">
                        Редактировать
                      </Link>
                      <button
                        type="button"
                        onClick={() => handleDelete(skill)}
                        className="text-accent-persimmon hover:underline"
                      >
                        Удалить
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AdminLayout>
  )
}
