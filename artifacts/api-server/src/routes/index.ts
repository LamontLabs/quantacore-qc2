import { Router, type IRouter } from "express";
import healthRouter from "./health";
import ownerCommandsRouter from "./ownerCommands";
import ownerReadRouter from "./ownerRead";

const router: IRouter = Router();

router.use(healthRouter);
router.use(ownerReadRouter);
router.use(ownerCommandsRouter);

export default router;
