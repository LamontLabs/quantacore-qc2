import { Router, type IRouter } from "express";
import healthRouter from "./health";
import ownerReadRouter from "./ownerRead";

const router: IRouter = Router();

router.use(healthRouter);
router.use(ownerReadRouter);

export default router;
