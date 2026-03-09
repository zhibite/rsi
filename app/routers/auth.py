from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, StrategyConfig
from ..schemas import UserRegister, UserLogin, Token, UserOut
from ..auth import hash_password, verify_password, create_access_token, get_current_user
from ..config import DEFAULT_PAIRS, settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if not settings.ALLOW_REGISTER:
        raise HTTPException(status_code=403, detail="Registration is closed")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.flush()

    # Create default strategy config with recommended risk control defaults
    default_strategy = StrategyConfig(
        user_id=user.id,
        pairs=DEFAULT_PAIRS,
        max_loss_pct=15.0,
        martin_cooldown_seconds=300,
    )
    db.add(default_strategy)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
