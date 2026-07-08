Predict the log-error of Zillow's Zestimate home valuation for properties in
Los Angeles, Orange, and Ventura counties, California. The log-error is defined
as log(Zestimate) - log(SalePrice). Minimise the Mean Absolute Error (MAE) on
a held-out validation set of Oct-Dec 2016 real-estate transactions.

The function build_and_predict(train_df, train_target, val_df) receives:
- train_df: pandas DataFrame (~70k rows) with property features. ALL columns
  are numeric (int/float) or datetime — no string/object columns. The column
  "logerror" is NOT present in train_df (it is the target, passed separately).
  Key columns include: bathroomcnt, bedroomcnt, roomcnt,
  calculatedfinishedsquarefeet, lotsizesquarefeet, yearbuilt, latitude,
  longitude, taxvaluedollarcnt, structuretaxvaluedollarcnt,
  landtaxvaluedollarcnt, taxamount, buildingqualitytypeid, garagecarcnt,
  poolcnt, fireplacecnt, numberofstories, unitcnt, fullbathcnt, fips,
  regionidcity, regionidcounty, regionidzip, calculatedbathnbr,
  threequarterbathnbr, censustractandblock.
  Also contains transactiondate (datetime) and parcelid (int64).
  Many columns have NaN values.
- train_target: pandas Series of logerror values (float, mean ~0, std ~0.06).
- val_df: same columns and dtypes as train_df (~20k rows).
Must return a numpy array of predicted logerror values with len(val_df)
elements.

IMPORTANT constraints:
- Do NOT access "logerror" from train_df — it does not exist there.
- All feature columns are numeric or datetime. No string encoding needed.
- Drop "parcelid" and "transactiondate" before fitting (they are IDs/dates).
  You may extract features from transactiondate (month, quarter) first.
- LightGBM handles NaN natively; for sklearn models, fill NaN explicitly.
- Keep total runtime under 180 seconds. Avoid KNN on full dataset; prefer
  vectorised operations.

Available libraries: numpy (as np), pandas (as pd), sklearn (scikit-learn),
lightgbm (import lightgbm as lgb), xgboost (import xgboost as xgb).

Strategies to explore:
- Feature engineering: ratios (taxamount / calculatedfinishedsquarefeet,
  bedroomcnt / bathroomcnt), age (2016 - yearbuilt), geographic clustering
  (latitude/longitude binning), temporal features from transactiondate
  (month, quarter), deviation from zip-code or county medians.
- Models: LightGBM (lgb.LGBMRegressor), XGBoost (xgb.XGBRegressor),
  sklearn GradientBoostingRegressor, RandomForest, Ridge, ElasticNet,
  or stacking / blending multiple models.
- Hyperparameters: learning_rate, n_estimators, max_depth, num_leaves,
  reg_alpha, reg_lambda, subsample, colsample_bytree, min_child_samples.
- Feature selection: drop columns with >50% NaN or low importance.
- Outlier handling: clip extreme logerror values during training.
- Ensembling: weighted average of LightGBM + XGBoost + Ridge.

A baseline predicting 0 gives MAE ~0.0675. Ridge regression gives ~0.0660.
Strong gradient-boosting solutions achieve MAE ~0.0650-0.0655.
numpy is available as np.
