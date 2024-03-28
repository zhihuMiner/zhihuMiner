# zhihuMiner
zhihuMiner is a tool to save questions and answers from zhihu for research purposes.

## Installing
1. Download, or clone this repository (`git clone https://github.com/zhihuMiner/zhihuMiner/`)
2. Install the requirements by running `pip install -r requirements.txt`

## Running the script
1. `zhihuMiner.py -qid <qid>` where `<qid>` is the question ID found in the URL of the question will download all answers, comments, and child comments and save them in a SQLite database in the same directory.
2. `zhihuMiner.py -har` will read from all `.har` files in the same directory and expects them to contain requests to `api/v4/search_v3`, which are made by searching for a topic on zhihu.
The `.har` files can be downloaded via the network tab (automating this step might make sense when searching for many questions, but the `api/v4/search_v3` route requires user authentication).
All questions in the `.har` files and their replies will be saved in a SQLite database.
4. `zhihuMiner.py -load` will continue the work started by `-qid` or `-har` after it was stopped or crashed

By default, there is a one-second delay between requests, but it can be adjusted [here](https://github.com/zhihuMiner/zhihuMiner/blob/79c1f2484ff55da3efb5a88223dde214f2441ec1/zhihuMiner.py#L22).

## License
zhihuMiner is licensed under the [MIT License](https://github.com/zhihuMiner/zhihuMiner/blob/79c1f2484ff55da3efb5a88223dde214f2441ec1/LICENSE).

