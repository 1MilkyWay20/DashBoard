"""资质更换任务：网页创建，本机 worker 领取并回报。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_app_db
from ..deps import authorize_brand, get_current_user
from ..models import QualificationJob, User
from ..schemas import QualificationJobOut, QualificationJobPatchIn

router = APIRouter(prefix="/qualification", tags=["qualification"])

# 证件图落盘目录（相对 backend 工作目录）
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "qualification"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_LICENSE_BYTES = 8 * 1024 * 1024
BRAND = "xj"


def _job_out(job: QualificationJob) -> dict:
    return QualificationJobOut.model_validate(job).model_dump()


def _save_license(file: UploadFile) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    raw_name = file.filename or "license.jpg"
    ext = Path(raw_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="证件图仅支持 jpg/png/webp/bmp")
    dest = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    size = 0
    with dest.open("wb") as f:
        while True:
            chunk = file.file.read(1024 * 64)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_LICENSE_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="证件图不能超过 8MB")
            f.write(chunk)
    return str(dest)


@router.post("/jobs")
async def create_job(
    mt_store_id: str = Form(""),
    elm_store_id: str = Form(""),
    jd_store_id: str = Form(""),
    tg_store_id: str = Form(""),
    operator_name: str = Form(...),
    credit_code: str = Form(...),
    legal_person: str = Form(...),
    address: str = Form(...),
    main_business_type: str = Form(...),
    business_scope: str = Form(...),
    valid_until: str = Form(...),
    license_no: str = Form(...),
    approved_at: str = Form(...),
    license: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    authorize_brand(user, BRAND)
    mt_store_id = mt_store_id.strip()
    elm_store_id = elm_store_id.strip()
    jd_store_id = jd_store_id.strip()
    tg_store_id = tg_store_id.strip()
    if not any((mt_store_id, elm_store_id, jd_store_id, tg_store_id)):
        raise HTTPException(status_code=400, detail="请至少填写一个平台门店ID")
    if not (license.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")

    license_path = _save_license(license)
    # 旧列 store_id 仍为 NOT NULL：写入首个非空平台 ID，避免插入失败
    primary_store_id = next(
        (x for x in (mt_store_id, elm_store_id, jd_store_id, tg_store_id) if x),
        "",
    )
    job = QualificationJob(
        brand=BRAND,
        store_id=primary_store_id,
        mt_store_id=mt_store_id,
        elm_store_id=elm_store_id,
        jd_store_id=jd_store_id,
        tg_store_id=tg_store_id,
        operator_name=operator_name.strip(),
        credit_code=credit_code.strip(),
        legal_person=legal_person.strip(),
        address=address.strip(),
        main_business_type=main_business_type.strip(),
        business_scope=business_scope.strip(),
        valid_until=valid_until.strip(),
        license_no=license_no.strip(),
        approved_at=approved_at.strip(),
        license_path=license_path,
        status="pending",
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(None, description="按状态过滤，如 pending"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    authorize_brand(user, BRAND)
    q = db.query(QualificationJob).filter(QualificationJob.brand == BRAND)
    if status:
        q = q.filter(QualificationJob.status == status)
    rows = q.order_by(QualificationJob.id.desc()).limit(100).all()
    return [_job_out(r) for r in rows]


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    authorize_brand(user, BRAND)
    job = db.get(QualificationJob, job_id)
    if job is None or job.brand != BRAND:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _job_out(job)


@router.post("/jobs/{job_id}/claim")
def claim_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    """原子领取：仅 pending 可变为 running，防止双 worker 抢同一任务。"""
    authorize_brand(user, BRAND)
    job = (
        db.query(QualificationJob)
        .filter(
            QualificationJob.id == job_id,
            QualificationJob.brand == BRAND,
            QualificationJob.status == "pending",
        )
        .with_for_update()
        .first()
    )
    if job is None:
        # 区分不存在 vs 已被领
        exists = db.get(QualificationJob, job_id)
        if exists is None or exists.brand != BRAND:
            raise HTTPException(status_code=404, detail="任务不存在")
        raise HTTPException(status_code=409, detail=f"任务状态为 {exists.status}，无法领取")
    job.status = "running"
    job.started_at = datetime.now()
    job.error_message = ""
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("/jobs/{job_id}/license")
def download_license(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    authorize_brand(user, BRAND)
    job = db.get(QualificationJob, job_id)
    if job is None or job.brand != BRAND:
        raise HTTPException(status_code=404, detail="任务不存在")
    path = Path(job.license_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="证件图文件不存在")
    return FileResponse(path, filename=path.name)


@router.patch("/jobs/{job_id}")
def patch_job(
    job_id: int,
    body: QualificationJobPatchIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_db),
):
    authorize_brand(user, BRAND)
    if body.status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="status 只能是 success 或 failed")
    job = db.get(QualificationJob, job_id)
    if job is None or job.brand != BRAND:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in ("running", "pending"):
        raise HTTPException(status_code=409, detail=f"任务已结束（{job.status}）")
    job.status = body.status
    job.error_message = (body.error_message or "")[:2000]
    job.finished_at = datetime.now()
    if job.started_at is None:
        job.started_at = job.finished_at
    db.commit()
    db.refresh(job)
    return _job_out(job)
