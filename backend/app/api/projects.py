import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evaluation import AIProject, EvaluationDataset, EvaluationRun, EvaluationRunStatus
from app.schemas import AIProjectCreate, AIProjectRead, ProjectEvaluationAccepted, ProjectEvaluationCreate
from app.services.project_evaluation import (
    allowed_auth_env_vars,
    execute_project_evaluation,
    validate_endpoint_url,
)

router = APIRouter(prefix="/projects", tags=["AI projects"])


@router.get("", response_model=list[AIProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[AIProject]:
    return list(db.scalars(select(AIProject).order_by(AIProject.created_at.desc())).all())


@router.post("", response_model=AIProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: AIProjectCreate, db: Session = Depends(get_db)) -> AIProject:
    try:
        validate_endpoint_url(payload.endpoint_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.auth_env_var and payload.auth_env_var not in allowed_auth_env_vars():
        raise HTTPException(
            status_code=422,
            detail="Authentication environment variable is not allowlisted by backend configuration",
        )
    project = AIProject(
        name=payload.name,
        endpoint_url=payload.endpoint_url,
        http_method=payload.http_method,
        request_template=payload.request_template,
        response_path=payload.response_path,
        auth_env_var=payload.auth_env_var,
        auth_header=payload.auth_header,
        auth_scheme=payload.auth_scheme,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/evaluations",
    response_model=ProjectEvaluationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_project_evaluation(
    payload: ProjectEvaluationCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
) -> ProjectEvaluationAccepted:
    project = db.get(AIProject, payload.project_id)
    dataset = db.get(EvaluationDataset, payload.dataset_id)
    if project is None:
        raise HTTPException(status_code=404, detail="AI project not found")
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    run = EvaluationRun(
        dataset_id=dataset.id,
        project_id=project.id,
        name=payload.name or f"{dataset.name} · {project.name}",
        status=EvaluationRunStatus.RUNNING,
        provider="project",
        model_name=project.name,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(
        execute_project_evaluation,
        db.get_bind(),
        run.id,
        project.id,
        request.state.request_id,
    )
    return ProjectEvaluationAccepted(run_id=run.id, status=run.status)


@router.get("/{project_id}", response_model=AIProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> AIProject:
    project = db.get(AIProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="AI project not found")
    return project
