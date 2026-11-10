from fastapi import FastAPI
from api.app.data_identity.routes import auth, activities, core_data, assets, users
from api.app.engine import routes as engine_routes
from api.app.analytics import routes as analytics_routes
from api.app.coach.routes import (
    chat as coach_chat, insights as coach_insights, learning as coach_learning,
    recommendations as coach_recs, whatif as coach_whatif,
)

app = FastAPI(title="CarbonLens API", version="1.0.0")

app.include_router(auth.router)
app.include_router(activities.router)
app.include_router(core_data.router)
app.include_router(assets.router)
app.include_router(users.router) # <-- Add this line
app.include_router(engine_routes.router)  # S2 Emission Engine
app.include_router(analytics_routes.router)  # S3 Analytics & Reporting

# S4 AI Sustainability Coach
app.include_router(coach_insights.router)
app.include_router(coach_recs.router)
app.include_router(coach_whatif.router)
app.include_router(coach_chat.router)
app.include_router(coach_learning.router)

@app.get("/")
def root():
    return {"message": "Welcome to CarbonLens API"}